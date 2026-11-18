// voice-lock.js — «Stick to my voice» (V2-651 F1): the switch, the enrolled voice, and the wire to the voice process.
//
// The speaker fingerprint (lib/speaker-id.js) enrols the first voice it hears on this device and judges every later
// speech segment against it. Until this switch it only MEASURED (shadow). With the switch ON, each verdict travels to
// the voice process (`zaelar-speaker`), whose attention gate drops a turn every segment of which was another voice
// (voice/voice_lock.py) — a TV, a person across the room never reaches the brain. Default OFF.
//
// Kept per DEVICE (localStorage), like the camera switch and the captions: the enrolled voice is a fingerprint of
// this microphone in this room, so it means nothing on another screen. With no voice enrolled the switch filters
// nothing, and the button says so.
import { createSignal } from "../core/reactive.js?v=2";

const KEY = "hb_voice_lock";
const PROFILE_KEY = "zaelar_spk_profile";

const _get = (k) => { try { return localStorage.getItem(k); } catch (_) { return null; } };
const _set = (k, v) => { try { localStorage.setItem(k, v); } catch (_) {} };

/** The profile of the enrolled voice, or null. Survives a reload: «the first voice enrolled at first start». */
export function loadProfile() {
  try {
    const p = JSON.parse(_get(PROFILE_KEY) || "null");
    return p && p.pitch && p.centroid ? p : null;
  } catch (_) { return null; }
}
export function saveProfile(p) {
  if (!p) return;
  const kept = { ...p, learned_at: p.learned_at || Date.now() };
  _set(PROFILE_KEY, JSON.stringify(kept)); setEnrolledRaw(true); setLearnedAt(kept.learned_at); sync();
}

const [on, setOnRaw] = createSignal(_get(KEY) === "1");          // no record = never touched = OFF
const [enrolled, setEnrolledRaw] = createSignal(!!loadProfile());
// When the kept voice was learned (ms), 0 = not learned or learned before the date was kept.
const [learnedAt, setLearnedAt] = createSignal((loadProfile() || {}).learned_at || 0);
export { on as voiceLock, enrolled as voiceEnrolled, learnedAt as voiceLearnedAt };

// «TRAIN MY VOICE» (Settings › Voice recognition, the ONLY place to re-learn it). The session registers the trainer,
// which owns the microphone's analyser: it sets the kept voice aside, enrols afresh from what he says now, and keeps
// the new voice only when the enrolment completes — a failed or abandoned one puts the old voice back. While it runs
// nothing is enrolled, so «Stick to my voice» filters nothing (the voice process hears `enrolled: false`).
const [training, setTraining] = createSignal(null);      // null | {count, need}
export { training as voiceTraining };
let _trainer = null;
export function useTrainer(fn) { _trainer = fn; }
/** Train afresh. Resolves {ok, why}: why = "no_session" (the agent is not listening here) | "timeout" | "stopped". */
export async function train({ timeoutMs = 30000 } = {}) {
  if (!_trainer) return { ok: false, why: "no_session" };
  if (training()) return { ok: false, why: "busy" };
  setTraining({ count: 0, need: 0 });
  const was = enrolled();
  setEnrolledRaw(false); sync();
  let r;
  try {
    r = await _trainer({ timeoutMs, onProgress: (count, need) => setTraining({ count, need }) });
  } catch (e) { r = { ok: false, why: String((e && e.message) || e) }; }
  setTraining(null);
  if (r && r.ok && r.profile) saveProfile({ ...r.profile, learned_at: Date.now() });
  else { setEnrolledRaw(was && !!loadProfile()); sync(); }
  import("./api.js?v=2").then((api) => api.uiEvent("voice:train", { ok: !!(r && r.ok), why: (r && r.why) || "" }))
    .catch(() => {});
  return r && r.ok ? { ok: true } : { ok: false, why: (r && r.why) || "failed" };
}

// The voice process hears the switch through one door the session registers (its data-channel publisher), and
// `ensure` starts the fingerprint if it was not running (it can be killed for the shadow; the switch needs it).
let _publish = null, _ensure = null;
export function useTransport(publish, ensure = null) { _publish = publish; _ensure = ensure; sync(); }
/** Re-assert the switch to the voice process (on connect and on every heartbeat, so a lost packet self-corrects). */
export function sync() {
  if (on() && _ensure) { try { _ensure(); } catch (_) {} }
  if (_publish) { try { _publish("zaelar-voicelock", { on: on(), enrolled: enrolled() }); } catch (_) {} }
}
/** One segment's verdict, sent only while the switch is on. `enroll` segments carry no verdict. */
export function verdict(label) {
  if (!on() || !_publish || !label || label === "enroll") return false;
  try { return _publish("zaelar-speaker", { label }) !== false; } catch (_) { return false; }
}

export function setVoiceLock(v, by = "ui") {
  const next = !!v;
  if (next === on()) return next;
  setOnRaw(next); _set(KEY, next ? "1" : "0"); sync();
  import("./api.js?v=2").then((api) => api.uiEvent("voice:lock:" + (next ? "on" : "off"), { by, enrolled: enrolled() }))
    .catch(() => {});
  return next;
}
export const toggleVoiceLock = (by = "ui") => setVoiceLock(!on(), by);

/** The tooltip's key: what the switch does NOW — off · on and filtering · on but nothing to filter against yet. */
export const lockTitleKey = () => (!on() ? "orb.voice_lock_off" : enrolled() ? "orb.voice_lock_on" : "orb.voice_lock_unenrolled");
