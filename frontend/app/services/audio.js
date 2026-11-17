// ============================================================================
// audio.js — Web Audio analysers + level math. Owns the AudioContext and the two
// AnalyserNodes (mic = person's voice, bot = zaelar's voice). The visualizer and
// the speaker-gate read these; the session service drives init/attach/reset.
//
// LIFECYCLE OBSERVABILITY (2026-08-10). This module is the ONLY owner of the analysers,
// so it is the only place where “attached” and “released” are truth rather than an
// assumption. The log used to record the bot track attach (🔈 TrackSubscribed) but
// NEVER its release, while for the mic it only showed the icon turning off—intent,
// not reality: a zombie speaker or an analyser surviving `stop()` left no trace.
// Emit ONLY on transitions (attach/release are discrete session operations, not render)
// and best-effort.
// ============================================================================
import * as api from "./api.js?v=2";

let ac = null, micAn = null, botAn = null, botStr = null;
// The agent's voice OUT through a gain (where the page cannot set an element's volume — iOS WebKit): source → gain →
// speakers. `null` while nothing is routed; then the <audio> element is the only way out and plays as before.
let outSrc = null, outGain = null, outLevel = 1;
let _outHook = null;
/** Who hears when the gain route appears or goes (services/volume.js re-holds the element: silent iff routed). */
export function onBotOutChange(fn) { _outHook = fn; }
const _outChanged = () => { try { if (_outHook) _outHook(); } catch (_) {} };
const _botListeners = new Set();
// V2-928 — the agent's face listens to the same stream (observe only): it subscribes here instead of re-wiring LiveKit.
export function onBotStream(fn) { _botListeners.add(fn); if (botStr) fn(botStr); return () => _botListeners.delete(fn); }
const _tellBot = (s) => { botStr = s; for (const fn of _botListeners) { try { fn(s); } catch (_) {} } };

export function context() { return ac; }
export function micAnalyser() { return micAn; }
export function botAnalyser() { return botAn; }

// Create the AudioContext + the mic analyser from the live stream. fftSize 2048 → enough for pitch (speaker gate).
export function initMic(stream) {
  // Without this, a null `stream` — the session was stopped mid-startup — surfaced as "Failed to execute
  // 'createMediaStreamSource': parameter 1 is not of type 'MediaStream'": a browser message that mentions neither
  // the session, nor ⏻, nor the stop, and that cost an operator a whole session read backwards. The error is still
  // thrown (there is no continuing from here), but it now says what actually happened.
  if (!(stream instanceof MediaStream)) {
    throw new Error("audio.initMic: no MediaStream — the voice session was stopped while starting up "
                    + `(received: ${stream === null ? "null" : typeof stream})`);
  }
  // A `start()` without a previous `stop()` (reconnection) left the previous AudioContext ALIVE and hanging:
  // Chrome caps pages at ~6, so a few reconnections made `new AudioContext()` throw → the mic meter and orb stayed
  // dead for the rest of the tab's lifetime. Close the previous one before opening another.
  if (ac) reset("reinit");
  ac = new (window.AudioContext || window.webkitAudioContext)();
  micAn = ac.createAnalyser(); micAn.fftSize = 2048;
  ac.createMediaStreamSource(stream).connect(micAn);
  api.uiState("mic:analyser", { state: "open", reason: "session_start" });
  return { ac, micAn };
}

// A microphone reopened after the operator closed it (`mic-device.js`): the same analyser listens to the new capture,
// and the AudioContext — with the bot's analyser on it — stays. Without a context yet, the full init.
export function rebindMic(stream) {
  if (!ac || !micAn) return initMic(stream);
  try { ac.createMediaStreamSource(stream).connect(micAn); } catch (_) {}
  return { ac, micAn };
}

// Attach the bot's returning audio to its own analyser (drives the orb). Best-effort.
// `routeOut`: the voice also LEAVES through this context's gain instead of the element (volume.js decides where that
// is needed). One source feeds both the analyser and the gain, and a new track replaces the previous route — two live
// routes would be the voice twice.
export function attachBot(stream, routeOut = false) {
  _unrouteOut();
  try {
    const src = ac.createMediaStreamSource(stream);
    botAn = ac.createAnalyser(); botAn.fftSize = 512; src.connect(botAn);
    if (routeOut) {
      outGain = ac.createGain(); outGain.gain.value = outLevel;
      src.connect(outGain); outGain.connect(ac.destination); outSrc = src;
    }
    api.uiState("audio:out", { state: "attached", route: outGain ? "gain" : "element" });
  } catch (_) { _unrouteOut(); }
  _tellBot(stream);
  _outChanged();
}

/** Is the voice leaving through the gain right now? (false ⇒ the element is the way out). */
export function botOutRouted() { return !!outGain; }

/** The gain's level, 0–1. Kept even with nothing routed, so the next route starts at it. */
export function setBotGain(v) {
  outLevel = Math.max(0, Math.min(1, Number(v) || 0));
  if (outGain) { try { outGain.gain.value = outLevel; } catch (_) {} }
}

function _unrouteOut() {
  const had = !!outGain;
  try { if (outSrc) outSrc.disconnect(); } catch (_) {}
  try { if (outGain) outGain.disconnect(); } catch (_) {}
  outSrc = null; outGain = null;
  return had;
}

/** Called inside the gesture that unlocks sound: a context the page opened before any touch may still be suspended. */
export function resumeContext() {
  try { if (ac && ac.state === "suspended" && ac.resume) return ac.resume().catch(() => {}); } catch (_) {}
  return Promise.resolve();
}

// Truly RELEASE: besides forgetting the nodes, CLOSE the AudioContext (releasing the browser's audio graph).
// `reason` says why, distinguishing a normal close from a reconnection.
export function reset(reason = "stop") {
  const had = { mic: !!micAn, bot: !!botAn };
  const old = ac;
  const routed = _unrouteOut();
  botAn = null; micAn = null; ac = null; if (had.bot) _tellBot(null);
  if (routed) _outChanged();
  try { if (old && old.state !== "closed" && old.close) old.close(); } catch (_) {}
  if (had.bot) api.uiState("audio:out", { state: "released" });
  if (had.mic) api.uiState("mic:analyser", { state: "closed", reason });
}
export function dropBot() {
  if (!botAn) return;                                    // already released: no transition to record
  const routed = _unrouteOut();
  botAn = null; _tellBot(null);
  if (routed) _outChanged();
  api.uiState("audio:out", { state: "released" });
}

// Average frequency magnitude (0..1) — used for orb/spectrum intensity.
export function level(an) {
  if (!an) return 0;
  const b = new Uint8Array(an.frequencyBinCount); an.getByteFrequencyData(b);
  let s = 0; for (let i = 0; i < b.length; i++) s += b[i]; return s / b.length / 255;
}

// True time-domain RMS of the mic (0..1-ish) — the on-screen "are you actually being heard" meter.
export function micRMS() {
  if (!micAn) return 0;
  const b = new Uint8Array(micAn.fftSize); micAn.getByteTimeDomainData(b);
  let s = 0; for (let i = 0; i < b.length; i++) { const v = (b[i] - 128) / 128; s += v * v; } return Math.sqrt(s / b.length);
}
