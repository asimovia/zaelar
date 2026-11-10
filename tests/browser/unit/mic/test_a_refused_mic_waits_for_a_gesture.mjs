// ============================================================================
// test_a_refused_mic_waits_for_a_gesture.mjs
//
// main.js re-enters `session.start()` from a reactive effect every time `starting` drops. A capture the browser
// refuses on the spot (denied, no device, a policy) failed instantly, `starting` dropped, start ran again: an endless
// loop of refused requests. After a refusal nothing asks the browser again until the person acts.
// And a refusal still gives a session: CHAT-ONLY on a silent stream, so his typed lines reach the engine.
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

// isRefusal: the same set the gate uses, and nothing transient.
assert.equal(D.isRefusal({ name: "NotAllowedError" }), true);
assert.equal(D.isRefusal({ name: "NotFoundError" }), true);
assert.equal(D.isRefusal({ name: "AbortError" }), false);
assert.equal(D.isRefusal(null), false);

// silentStream: a muted oscillator into a stream destination, marked, and its track's stop closes the context.
const seen = { started: 0, closed: 0, gain: null };
const track = { readyState: "live", stop() { this.readyState = "ended"; } };
globalThis.window.AudioContext = class {
  createOscillator() { return { connect: (n) => n, start: () => { seen.started++; } }; }
  createGain() { const g = { gain: { value: 1 }, connect: (n) => n }; seen.gain = g.gain; return g; }
  createMediaStreamDestination() { return { stream: { getAudioTracks: () => [track], getTracks: () => [track] } }; }
  close() { seen.closed++; return Promise.resolve(); }
};
const s = D.silentStream();
assert.equal(s.__silent, true, "the stream says it is silent");
assert.equal(seen.gain.value, 0, "it carries no sound");
assert.equal(seen.started, 1, "the oscillator runs, so the track is live");
s.getAudioTracks()[0].stop();
assert.equal(track.readyState, "ended");
assert.equal(seen.closed, 1, "stopping the track closes the audio context behind it");
delete globalThis.window.AudioContext;
assert.throws(() => D.silentStream(), "with no audio context it throws, and the refusal stands");
console.log("ok");
