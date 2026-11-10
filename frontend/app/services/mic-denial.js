// ============================================================================
// mic-denial.js — after the browser refuses the microphone, nothing asks again until the person acts.
//
// `session.start()` is re-entered by a reactive effect in main.js every time `starting` drops. A capture that the
// browser refuses on the spot (permission denied, no device, a policy) made start fail instantly, `starting` dropped,
// the effect ran start again: hundreds of thousands of refused requests in minutes, the tab busy doing nothing else.
// A refusal is not transient — only a gesture (the person clicking, pressing a key, granting it) can change it.
// ============================================================================
const _s = { denied: false };
const REFUSALS = new Set(["NotAllowedError", "SecurityError", "NotFoundError", "NotReadableError", "OverconstrainedError"]);

/** Record a capture error; true when it is a refusal that must wait for a gesture. */
export function noteCaptureError(err) {
  const refused = REFUSALS.has(err && err.name);
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
