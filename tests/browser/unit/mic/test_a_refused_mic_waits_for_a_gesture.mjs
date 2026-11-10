// ============================================================================
// test_a_refused_mic_waits_for_a_gesture.mjs
//
// main.js re-enters `session.start()` from a reactive effect every time `starting` drops. A capture the browser
// refuses on the spot (denied, no device, a policy) failed instantly, `starting` dropped, start ran again: an endless
// loop of refused requests. After a refusal nothing asks the browser again until the person acts.
//
// Run: node tests/browser/unit/mic/test_a_refused_mic_waits_for_a_gesture.mjs
// ============================================================================
import assert from "node:assert/strict";

const listeners = {};
globalThis.window = { addEventListener: (ev, fn) => { (listeners[ev] ||= []).push(fn); } };
const D = await import("../../../../frontend/app/services/mic-denial.js?v=1");

assert.equal(D.waitingForGesture(), false);
for (const name of ["NotAllowedError", "SecurityError", "NotFoundError", "NotReadableError", "OverconstrainedError"]) {
  assert.equal(D.noteCaptureError({ name }), true, name);
  assert.equal(D.waitingForGesture(), true, `${name} waits for a gesture`);
  listeners.pointerdown.forEach((fn) => fn());
  assert.equal(D.waitingForGesture(), false, "a click lets the next start ask again");
}
assert.equal(D.noteCaptureError({ name: "AbortError" }), false, "a transient error is not a refusal");
assert.equal(D.waitingForGesture(), false);
D.noteCaptureError({ name: "NotAllowedError" });
listeners.keydown.forEach((fn) => fn());
assert.equal(D.waitingForGesture(), false, "a key is a gesture too");
console.log("ok");
