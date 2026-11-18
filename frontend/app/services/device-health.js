// ============================================================================
// device-health.js — is the microphone capturing, and can the agent's voice come out? (V2-788)
//
// THE GAP THIS CLOSES. Mid-session the agent's voice stopped being heard while the engine kept synthesising it
// normally. The browser had reported three lines at connect time (TrackSubscribed, the element state after
// attach, play() OK) and NOTHING afterwards, so nobody could tell whether the <audio> element paused, the remote
// track went muted or ended, the audio context was interrupted, the output device changed or vanished, or
// playback was blocked. The microphone had the same blind spot (permission revoked, track ended, device gone).
//
// WHAT THIS MODULE IS. The only writer of `store.deviceConds`: every detector below turns a browser event into a
// named CONDITION on one device ("mic" | "spk"), and every condition change is reported ONCE through the
// existing client-log channel (`kind=client`, device + state + detail) — on change, never periodically. The
// verdict the orb paints is derived in the store (`store.micHealth()` / `store.spkHealth()`), so a condition
// clearing clears the red with no extra code, and a deliberate mute is decided in one place.
//
// It never moves audio and never mutes anything: it watches. The one action it takes is RECOVERY on a user
// gesture (the injected `recover`, i.e. `session.unlockAudio()` + resuming the analyser context), because a
// browser only lets a page restart playback from inside a gesture.
//
// WHAT A PAGE CANNOT SEE. The silence detector measures the audio the browser RECEIVED, not what left the
// speakers: OS volume at zero, the system output muted, or another application taking exclusive hold of the
// device downstream of the browser all look healthy from here. Output device lists exist only where the browser
// enumerates `audiooutput` (Chromium); `interrupted` exists only on Safari; the permissions API may not know
// «microphone» on older engines. Those gaps report nothing rather than guess.
// ============================================================================
import * as store from "../core/store.js?v=2";
import * as api from "./api.js?v=2";

// Speech the engine says is playing, with no energy in the RECEIVED remote audio for this long, is the signature
// of «I can't hear it» that no element event carries (a live track can deliver pure silence).
export const SILENCE_MS = 4000;
// Average spectral magnitude (audio.level(), 0..1) above which the received audio counts as carrying sound.
export const ENERGY_MIN = 0.01;

const _ICON = { mic: "🎤", spk: "🔈" };

// The i18n key that names each reason on the icon's title — literal keys, so a bundle check can find them.
const _TITLE_KEYS = {
  mic: { permission_denied: "orb.mic_problem_permission", no_device: "orb.mic_problem_no_device",
         capture_error: "orb.mic_problem_capture", track_ended: "orb.mic_problem_track_ended",
         track_muted: "orb.mic_problem_track_muted", no_agent: "orb.mic_problem_no_agent" },
  spk: { blocked: "orb.spk_problem_blocked", track_ended: "orb.spk_problem_track_ended",
         element_error: "orb.spk_problem_element_error", paused: "orb.spk_problem_paused",
         context_interrupted: "orb.spk_problem_interrupted", no_output: "orb.spk_problem_no_output",
         sink_lost: "orb.spk_problem_sink_lost", silent_while_speaking: "orb.spk_problem_silent",
         remote_muted: "orb.spk_problem_remote_muted" },
};
export const problemTitleKey = (device, reason) => (_TITLE_KEYS[device] || {})[reason] || "orb.device_problem";

// The ONE writer. Reports only real transitions; returns whether anything changed.
export function setCondition(device, cond, active, detail = "") {
  const all = store.deviceConds() || { mic: {}, spk: {} };
  const cur = { ...(all[device] || {}) };
  const had = cond in cur;
  if (active === had && (!active || cur[cond] === String(detail || ""))) return false;
  if (active) cur[cond] = String(detail || ""); else delete cur[cond];
  store.setDeviceConds({ ...all, [device]: cur });
  const verdict = store.deviceHealth(device);
  try {
    api.clientLog(`${_ICON[device]} ${device} health: ${active ? "problem " + cond : cond + " cleared"}`, {
      device,
      state: (active ? "problem:" : "clear:") + cond,
      text: `${detail ? String(detail).slice(0, 160) + " · " : ""}verdict=${verdict.ok ? "ok" : verdict.reason}`,
    });
  } catch (_) {}
  return true;
}

// A report-only event (no colour): deduped by key so a repeated identical value is not reported twice.
const _lastNote = new Map();
export function note(device, key, value, detail = "") {
  const v = String(value);
  if (_lastNote.get(device + ":" + key) === v) return false;
  _lastNote.set(device + ":" + key, v);
  try { api.clientLog(`${_ICON[device]} ${device} ${key}: ${v}`, { device, state: key + ":" + v, text: String(detail || "").slice(0, 200) }); } catch (_) {}
  return true;
}

// A session that ends takes its session-scoped conditions with it; a revoked permission or an absent device is
// a fact about the browser, not the session, and stays until its own detector clears it.
const _PERSISTENT = { mic: ["permission_denied", "no_device"], spk: ["no_output"] };
export function clearSession() {
  for (const device of ["mic", "spk"]) {
    for (const cond of Object.keys((store.deviceConds() || {})[device] || {})) {
      if (!_PERSISTENT[device].includes(cond)) setCondition(device, cond, false, "session ended");
    }
  }
  _speakingSince = 0; _lastEnergyAt = 0;
}

// ── MICROPHONE ────────────────────────────────────────────────────────────────────────────────────────────
// getUserMedia outcome. NotReadableError is the browser's own way of saying «another application holds the
// device»; NotFound/Overconstrained = no usable input; NotAllowed = denied.
export function micCaptureResult(err) {
  if (!err) {
    for (const c of ["capture_error", "no_device", "permission_denied"]) setCondition("mic", c, false, "getUserMedia ok");
    return;
  }
  const n = String((err && err.name) || err);
  const d = `${n}: ${String((err && err.message) || "")}`;
  if (n === "NotAllowedError" || n === "SecurityError") setCondition("mic", "permission_denied", true, d);
  else if (n === "NotFoundError" || n === "OverconstrainedError") setCondition("mic", "no_device", true, d);
  else setCondition("mic", "capture_error", true, d);
}

// The captured track. `mute` on a LOCAL track is the SOURCE going silent (OS privacy switch, another app taking
// the device) — not our mute, which flips `enabled` and fires nothing. A new track starts clean.
//
// 2026-11-16 — A DEAD TRACK IS TAKEN AGAIN, NOT ONLY PAINTED. iOS ends (or mutes and never unmutes) the capture track
// when it interrupts the audio session (a call, Siri, another app, the app coming back from the background); the page
// went on publishing a dead track and nobody asked for the microphone again — a session stayed deaf for nine minutes
// with the condition sitting in the store. So a track that ENDS, or stays muted by its source for `MUTE_GRACE_MS`, is
// LOST, and the lost hook (`onMicLost`, installed by the session engine) takes the device again. The same check runs
// when the page comes back to the front and when the audio context leaves an interruption: iOS ends the track while
// the page is frozen and the event may never be delivered.
//
// 2026-11-18 — NOT DURING THE INTERRUPTION. Measured on iOS (b154): the grace timer and the context check revived the mic
// while the audio session was still interrupted; the fresh track was born muted, nobody looked again when the
// interruption ended, and the session stayed deaf. So a loss found while the context is `interrupted` WAITS, and the
// end of the interruption (the track unmuting, or the context leaving `interrupted`) revives once. A track born muted
// gets the same grace as one muted later, and the end of an interruption resumes the context — on iOS the agent's
// voice leaves through it (V2-930), so an interruption silenced him too.
export const MUTE_GRACE_MS = 1500;
let _micTrack = null, _onLost = null, _muteTimer = null, _waiting = false;
const _setT = (fn, ms) => setTimeout(fn, ms), _clearT = (t) => clearTimeout(t);
/** The session engine's reaction to a lost capture track: `fn(why)` takes the device again. */
export function onMicLost(fn) { _onLost = typeof fn === "function" ? fn : null; }
function _lost(why) {
  if (!_onLost) return;
  note("mic", "lost", why + ":" + Date.now(), String((_micTrack && _micTrack.label) || "").slice(0, 80));
  try { _onLost(why); } catch (_) {}
}
/** Is the watched capture track dead (ended, or muted by its source)? Asked on visibility and context changes. */
export function micTrackDead() {
  const tr = _micTrack;
  return !!tr && (tr.readyState === "ended" || !!tr.muted);
}
const _interrupted = () => !!_ctx && _ctx.state === "interrupted";
function _lostOrWait(why) {
  if (!_interrupted()) { _lost(why); return; }
  if (!_waiting) note("mic", "lost", "waiting_interruption:" + why + ":" + Date.now());
  _waiting = true;
}
function _interruptionEnded(why) {
  try { if (_ctx && _ctx.state !== "running" && _ctx.state !== "closed" && _ctx.resume) _ctx.resume().catch(() => {}); } catch (_) {}
  if (!_waiting) return false;
  _waiting = false;
  _lost(why);
  return true;
}
export function checkMicAlive(why) { if (micTrackDead()) _lostOrWait(why); }
export function watchMicTrack(track, { setT = _setT, clearT = _clearT } = {}) {
  if (!track || track === _micTrack) return;
  _micTrack = track; _waiting = false;
  if (_muteTimer) { clearT(_muteTimer); _muteTimer = null; }
  setCondition("mic", "track_ended", false, "new track");
  setCondition("mic", "track_muted", !!track.muted, track.muted ? "born muted by its source" : "new track");
  const label = () => String(track.label || "").slice(0, 80);
  const armMute = () => {
    if (_muteTimer) clearT(_muteTimer);
    _muteTimer = setT(() => { _muteTimer = null; if (_micTrack === track && track.muted) _lostOrWait("track_muted"); },
                      MUTE_GRACE_MS);
  };
  if (track.muted) armMute();
  track.addEventListener("ended", () => {
    if (_micTrack !== track) return;
    setCondition("mic", "track_ended", true, label());
    _lostOrWait("track_ended");
  });
  track.addEventListener("mute", () => {
    if (_micTrack !== track) return;
    setCondition("mic", "track_muted", true, label());
    armMute();
  });
  track.addEventListener("unmute", () => {
    if (_micTrack !== track) return;
    if (_muteTimer) { clearT(_muteTimer); _muteTimer = null; }
    setCondition("mic", "track_muted", false, label());
    _interruptionEnded("track_unmuted");
  });
}

// The permission, where the browser exposes it, with its live onchange: a revocation mid-session is reported
// the moment it happens instead of surfacing as an unexplained silence.
export async function watchMicPermission(nav = globalThis.navigator) {
  try {
    if (!nav || !nav.permissions || !nav.permissions.query) return null;
    const status = await nav.permissions.query({ name: "microphone" });
    const apply = () => {
      note("mic", "permission", status.state);
      setCondition("mic", "permission_denied", status.state === "denied", "permissions.query=" + status.state);
    };
    apply();
    if (status.addEventListener) status.addEventListener("change", apply); else status.onchange = apply;
    return status;
  } catch (_) { return null; }   // Firefox/older Safari may not know the name — the getUserMedia result still reports
}

// ── SPEAKER ───────────────────────────────────────────────────────────────────────────────────────────────
// The bot's <audio> element. A pause is only a fault while a session is up with a stream attached: `stop()`
// pauses it deliberately and drops srcObject, and that must not paint anything.
let _botEl = null;
export function watchBotElement(el) {
  if (!el || el === _botEl || !el.addEventListener) return;
  _botEl = el;
  const live = () => !!(store.started() && el.srcObject);
  el.addEventListener("pause", () => { if (live()) setCondition("spk", "paused", true, "audio element paused"); });
  el.addEventListener("playing", () => {
    setCondition("spk", "paused", false, "playing");
    setCondition("spk", "element_error", false, "playing");
    note("spk", "element", "playing");
  });
  el.addEventListener("ended", () => { if (live()) setCondition("spk", "paused", true, "audio element ended"); });
  el.addEventListener("error", () => {
    const e = el.error; setCondition("spk", "element_error", true, e ? `code=${e.code} ${e.message || ""}` : "error");
  });
  // Buffering signals are reported, not painted: on a WebRTC stream they can be transient.
  for (const ev of ["stalled", "waiting"]) el.addEventListener(ev, () => { if (live()) note("spk", "element", ev); });
}

// The agent's remote track. Its MediaStreamTrack `mute` is «no media is arriving»: between utterances that is
// normal silence, so it only counts while the engine says the agent is speaking (store WHILE_SPEAKING).
let _remoteTrack = null;
export function watchRemoteTrack(mst) {
  if (!mst || mst === _remoteTrack) return;
  _remoteTrack = mst;
  setCondition("spk", "track_ended", false, "new remote track");
  setCondition("spk", "remote_muted", !!mst.muted, "new remote track");
  mst.addEventListener("ended", () => { if (_remoteTrack === mst) setCondition("spk", "track_ended", true, "remote track ended"); });
  mst.addEventListener("mute", () => { if (_remoteTrack === mst) setCondition("spk", "remote_muted", true, "no media arriving"); });
  mst.addEventListener("unmute", () => { if (_remoteTrack === mst) setCondition("spk", "remote_muted", false, "media arriving"); });
}

// The analyser context's state. `interrupted` (Safari) is the OS handing the audio session to someone else;
// `suspended` is reported, not painted — playback goes through the <audio> element, not this context — but
// while it is not running the silence detector below refuses to judge (an idle analyser reads zeros).
let _ctx = null;
export function watchAudioContext(ctx) {
  if (!ctx || ctx === _ctx) return;
  _ctx = ctx;
  let was = ctx.state;
  const apply = () => {
    if (_ctx !== ctx) return;
    note("spk", "context", ctx.state);
    setCondition("spk", "context_interrupted", ctx.state === "interrupted", "AudioContext=" + ctx.state);
    const ended = was === "interrupted" && ctx.state !== "interrupted";
    was = ctx.state;
    if (ended && _interruptionEnded("context_" + ctx.state)) return;
    if (ctx.state === "running") checkMicAlive("context_running");   // out of an interruption: is the mic still ours?
  };
  apply();
  try { ctx.addEventListener("statechange", apply); } catch (_) {}
}

// SILENT WHILE SPEAKING. One step of the detector, driven by a timer in the browser and by hand in tests:
// `level` is the received remote audio's energy, `ctxState` the analyser context's state.
let _speakingSince = 0, _lastEnergyAt = 0;
export function tickSilence({ now, level, ctxState }) {
  if (!store.started() || store.botMuted() || ctxState !== "running") { _speakingSince = 0; return; }
  if (Number(level) > ENERGY_MIN) {
    _lastEnergyAt = now;
    setCondition("spk", "silent_while_speaking", false, "energy back");
    return;
  }
  if (!store.botSpeaking()) { _speakingSince = 0; return; }
  if (!_speakingSince) _speakingSince = now;
  const quietFor = now - Math.max(_speakingSince, _lastEnergyAt);
  if (quietFor >= SILENCE_MS) {
    setCondition("spk", "silent_while_speaking", true, `agent speaking, no received energy for ${Math.round(quietFor / 1000)}s`);
  }
}

// Output devices. Chrome lists `audiooutput` entries (others list none): a list that HAD outputs and now has
// zero, or an explicitly chosen sink that left the list, means sound is going nowhere. A change of the
// default output (headphones connecting, another app's device) is reported — it is the commonest «I can't
// hear it» that a page cannot otherwise see.
let _sawOutputs = false;
export async function checkDevices(nav = globalThis.navigator) {
  try {
    if (!nav || !nav.mediaDevices || !nav.mediaDevices.enumerateDevices) return;
    const list = await nav.mediaDevices.enumerateDevices();
    const ins = list.filter(d => d.kind === "audioinput");
    const outs = list.filter(d => d.kind === "audiooutput");
    note("mic", "inputs", ins.length);
    setCondition("mic", "no_device", ins.length === 0, "no audioinput listed");
    if (_micTrack && _micTrack.getSettings) {
      const id = (_micTrack.getSettings() || {}).deviceId;
      if (id && ins.length && !ins.some(d => d.deviceId === id)) note("mic", "device", "gone", String(_micTrack.label || ""));
    }
    if (outs.length) _sawOutputs = true;
    if (_sawOutputs) {
      const def = outs.find(d => d.deviceId === "default") || outs[0];
      note("spk", "default_output", def ? String(def.label || def.groupId || "?").slice(0, 80) : "none");
      setCondition("spk", "no_output", outs.length === 0, "no audiooutput listed");
      const sink = _botEl && _botEl.sinkId;
      setCondition("spk", "sink_lost", !!(sink && sink !== "default" && !outs.some(d => d.deviceId === sink)),
                   "sinkId " + String(sink || "").slice(0, 12) + " left the device list");
    }
  } catch (_) {}
}

// ── INSTALL (once per page) ───────────────────────────────────────────────────────────────────────────────
let _installed = false;
export function install({ recover, level, ctxState, nav = globalThis.navigator } = {}) {
  if (_installed) return;
  _installed = true;
  watchMicPermission(nav);
  try { nav.mediaDevices.addEventListener("devicechange", () => checkDevices(nav)); } catch (_) {}
  checkDevices(nav);
  try {
    document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") checkMicAlive("visible"); });
    window.addEventListener("pageshow", () => checkMicAlive("pageshow"));
  } catch (_) {}
  if (level && ctxState) setInterval(() => { try { tickSilence({ now: Date.now(), level: level(), ctxState: ctxState() }); } catch (_) {} }, 250);
  // RECOVERY must run inside the gesture's call stack, so it hangs off pointerdown, and only does anything while
  // the speaker actually has a problem.
  if (recover) {
    try { window.addEventListener("pointerdown", () => { if (!store.spkHealth().ok) recoverNow(recover, "gesture"); }, true); } catch (_) {}
  }
}

export function recoverNow(recover, why = "gesture") {
  const h = store.spkHealth();
  note("spk", "recovery", why + ":" + (h.reason || "ok") + ":" + Date.now(), "re-unlocking playback");
  try { return recover(); } catch (_) { return null; }
}
