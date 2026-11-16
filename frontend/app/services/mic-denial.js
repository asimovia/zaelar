// ============================================================================
// mic-denial.js — after the browser refuses the microphone, nothing asks again until the person acts.
//
// `session.start()` is re-entered by a reactive effect in main.js every time `starting` drops. A capture that the
// browser refuses on the spot (permission denied, no device, a policy) made start fail instantly, `starting` dropped,
// the effect ran start again: hundreds of thousands of refused requests in minutes, the tab busy doing nothing else.
// A refusal is not transient — only a gesture (the person clicking, pressing a key, granting it) can change it.
// And a refusal is no reason to have no session: without one the engine takes no typed line either, so a start the
// mic refuses comes up CHAT-ONLY on a silent stream (`silentStream`) instead of failing.
// ============================================================================
const _s = { denied: false };
const REFUSALS = new Set(["NotAllowedError", "SecurityError", "NotFoundError", "NotReadableError", "OverconstrainedError"]);

/** True for a capture error the browser repeats until the person acts (not a transient failure). */
export const isRefusal = (err) => REFUSALS.has(err && err.name);
/** A silent audio stream (`__silent`): a session with no mic still joins its room, so his typed lines reach the
 *  engine. Stopping its track closes the audio context behind it. Throws where there is no audio context. */
export function silentStream() {
  const Ctx = window.AudioContext || window.webkitAudioContext;
  const ctx = new Ctx();
  const osc = ctx.createOscillator(), gain = ctx.createGain(), dst = ctx.createMediaStreamDestination();
  gain.gain.value = 0;
  osc.connect(gain).connect(dst); osc.start();
  const s = dst.stream; s.__silent = true;
  const tr = s.getAudioTracks()[0];
  if (tr) { const stop = tr.stop.bind(tr); tr.stop = () => { stop(); try { ctx.close(); } catch (_) {} }; }
  return s;
}
/** Record a capture error; true when it is a refusal that must wait for a gesture. */
export function noteCaptureError(err) {
  const refused = isRefusal(err);
  if (refused) _s.denied = true;
  return refused;
}
/** True while a refusal waits for a gesture: start() returns without asking the browser again. */
export const waitingForGesture = () => _s.denied;
/** A gesture: the next start() may ask again. */
export const gesture = () => { _s.denied = false; };
try {
  for (const ev of ["pointerdown", "keydown"]) window.addEventListener(ev, gesture, { capture: true, passive: true });
} catch (_) {}

// WHERE HE ALLOWS IT (2026-11-16). Once the system has refused the microphone and no longer asks, the page cannot ask
// again: the only way out is a setting he changes himself. One sentence per kind of surface says where, and the native
// app opens its own settings page (`app-settings:`, which the iOS shell hands to the system: any URL outside the app's
// origin opens outside the WebView). Read from the page itself: the native shell marks <html class="in-app"
// data-platform="ios|android"> before any script runs (mobile-app/www/in-app.js).
/** `{ key, open }`: the i18n key of the sentence, and the URL to open ('' when the surface has none). */
export function settingsHint(doc = globalThis.document, nav = globalThis.navigator) {
  const root = doc && doc.documentElement;
  const inApp = !!(root && root.classList && root.classList.contains("in-app"));
  const platform = (root && root.getAttribute && root.getAttribute("data-platform")) || "";
  if (inApp && platform === "ios") return { key: "voice.mic_allow_app_ios", open: "app-settings:" };
  if (inApp) return { key: "voice.mic_allow_app_android", open: "" };
  const ua = String((nav && nav.userAgent) || "");
  if (/iPhone|iPad|iPod/.test(ua)) return { key: "voice.mic_allow_ios_safari", open: "" };
  return { key: "voice.mic_allow_browser", open: "" };
}
