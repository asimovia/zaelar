// ============================================================================
// test_a_mic_revived_during_an_interruption_is_not_deaf.mjs — an iOS audio interruption must not leave the mic deaf.
//
// MEASURED (iOS, b154). An interruption (context `interrupted`, capture track muted, 70 s): the page revived the mic
// DURING it, the fresh track was born muted, was swapped into the sender, and the log said «reopened». When the
// interruption ended the orb moved (the analyser had BOTH captures stacked) while the server got pure silence.
//
// Driven over the REAL modules (`device-health.js`, `mic-device.js`, `mic-wire.js`, `audio.js`) with fakes:
//   1. a loss inside an interruption WAITS; the end (context leaving `interrupted`, or the track unmuting) revives ONCE
//      and resumes the context (the agent's voice leaves through it on iOS);
//   2. a track BORN muted gets the grace and is lost like one muted later;
//   3. a revive stops the old capture before asking for the device;
//   4. a revive is PROVED: born muted → republished; nothing on the wire → the session restarts; «reopened» only proved;
//   5. the mic analyser listens to ONE capture after a rebind;
//   6. a republish unpublishes keeping the track alive and publishes it again.
//
// Run: node tests/browser/unit/voice/test_a_mic_revived_during_an_interruption_is_not_deaf.mjs
// ============================================================================
import assert from "node:assert/strict";

const mem = new Map([["hb_lang", "en"]]);
globalThis.localStorage = { getItem: k => (mem.has(k) ? mem.get(k) : null),
                            setItem: (k, v) => mem.set(k, String(v)), removeItem: k => mem.delete(k) };
globalThis.fetch = async () => ({ ok: true, json: async () => ({}), text: async () => "" });
globalThis.document = { documentElement: { lang: "en", setAttribute(){}, style: { setProperty(){} } },
                        querySelectorAll: () => [], querySelector: () => null, addEventListener(){} };
globalThis.window = { addEventListener(){}, location: { href: "http://localhost/" } };

const store = await import("../../../../frontend/app/core/store.js?v=2");
const health = await import("../../../../frontend/app/services/device-health.js?v=1");
const { createMicDevice, VERIFY_MS, VERIFY_STEP_MS } = await import("../../../../frontend/app/services/mic-device.js?v=1");
const { republishMic } = await import("../../../../frontend/app/services/mic-wire.js?v=1");

class FakeTrack extends EventTarget {
  constructor(label) { super(); this.label = label; this.muted = false; this.readyState = "live"; this.enabled = true; this.stopped = false; }
  stop() { this.stopped = true; this.readyState = "ended"; }
  fire(type) {
    if (type === "mute") this.muted = true;
    if (type === "unmute") this.muted = false;
    this.dispatchEvent(new Event(type));
  }
}
class FakeCtx extends EventTarget {
  constructor(state) { super(); this.state = state; this.resumes = 0; }
  go(state) { this.state = state; this.dispatchEvent(new Event("statechange")); }
  resume() { this.resumes += 1; return Promise.resolve(); }
}
let clock = 0; const timers = new Map(); let nextId = 1;
const setT = (fn, ms) => { const id = nextId++; timers.set(id, { at: clock + ms, fn }); return id; };
const clearT = (id) => timers.delete(id);
const advance = (ms) => { clock += ms; for (const [id, t] of [...timers]) if (t.at <= clock) { timers.delete(id); t.fn(); } };

store.setStarted(true); store.setMicMuted(false);
const lost = [];
health.onMicLost((why) => lost.push(why));

// ══ 1a · a loss inside an interruption waits; the context leaving it revives ONCE ═══════════════════════════
const c1 = new FakeCtx("running");
health.watchAudioContext(c1);
const t1 = new FakeTrack("iPhone Microphone");
health.watchMicTrack(t1, { setT, clearT });
c1.go("interrupted");
t1.fire("mute");
advance(health.MUTE_GRACE_MS + 1);
assert.deepEqual(lost, [], "no revive while the track is muted and the context interrupted: the new track is born muted");
health.checkMicAlive("visible");
assert.deepEqual(lost, [], "…nor from a visibility check inside the interruption");
c1.go("running");
assert.deepEqual(lost, ["context_running"], "the end of the interruption revives ONCE");

// ══ 1b · the track unmuting ends it too, and the context is resumed (iOS: the agent's voice goes through it) ══
const c2 = new FakeCtx("running");
health.watchAudioContext(c2);            // (a fresh context finds t1 still muted: that is 1a's track, not this case)
const t2 = new FakeTrack("iPhone Microphone");
health.watchMicTrack(t2, { setT, clearT });
lost.length = 0;
c2.go("interrupted");
t2.fire("mute");
advance(health.MUTE_GRACE_MS + 1);
assert.deepEqual(lost, []);
t2.fire("unmute");
assert.deepEqual(lost, ["track_unmuted"], "the track unmuting is the end of the interruption: one revive");
assert.ok(c2.resumes >= 1, "the context left interrupted is resumed, or the agent stays mute on iOS");
t2.fire("mute"); t2.fire("unmute");
assert.deepEqual(lost, ["track_unmuted"], "a later blip outside an interruption revives nothing");

// ══ 2 · a track BORN muted gets the grace, then is lost ═══════════════════════════════════════════════════════
health.watchAudioContext(new FakeCtx("running"));   // the interruption is over
lost.length = 0;
const t3 = new FakeTrack("iPhone Microphone"); t3.muted = true;
health.watchMicTrack(t3, { setT, clearT });
assert.equal(store.micHealth().reason, "track_muted");
advance(health.MUTE_GRACE_MS + 1);
assert.deepEqual(lost, ["track_muted"], "a track born muted by its source is retried, not only painted");

// ══ 3 · a revive stops the old capture before asking for the device ══════════════════════════════════════════
const old = new FakeTrack("old");
let stoppedFirst = null;
const d3 = createMicDevice({
  current: () => ({ getAudioTracks: () => [old] }),
  acquire: async () => { stoppedFirst = old.stopped; return { getAudioTracks: () => [new FakeTrack("fresh")], getTracks: () => [] }; },
  adopt: async () => {},
});
assert.equal(await d3.revive(), true);
assert.equal(stoppedFirst, true, "the old track is stopped BEFORE getUserMedia (a live old capture keeps the session)");

// ══ 4 · a revive is PROVED on the wire ═══════════════════════════════════════════════════════════════════════
function rig(states, { stale = () => false } = {}) {
  const logs = [], calls = []; let i = 0;
  const dev = createMicDevice({
    acquire: async () => ({ getAudioTracks: () => [], getTracks: () => [] }),
    adopt: async () => calls.push("adopt"),
    log: (w) => logs.push(w),
    probe: async () => states[Math.min(i++, states.length - 1)],
    republish: async () => calls.push("republish"),
    restart: async () => calls.push("restart"),
    wait: async () => {},
  });
  return { dev, logs, calls, stale };
}
const OK = { muted: false, level: 0.03 }, MUTED = { muted: true, level: 0 }, SILENT = { muted: false, level: 0 };
let r = rig([OK]);
assert.equal(await r.dev.revive(), true);
assert.deepEqual(r.calls, ["adopt"]); assert.ok(r.logs.includes("reopened"), "audio on the wire: reopened");
r = rig([MUTED, OK]);
assert.equal(await r.dev.revive(), true);
assert.deepEqual(r.calls, ["adopt", "republish"], "a track born muted is republished");
assert.ok(r.logs.includes("republish_born_muted") && r.logs.includes("reopened"));
r = rig([SILENT]);
assert.equal(await r.dev.revive(), true, "handled: the session restarts");
assert.deepEqual(r.calls, ["adopt", "republish", "restart"], "nothing on the wire after a republish restarts the session");
assert.ok(!r.logs.includes("reopened"), "«reopened» is said only when audio is proved to leave");
assert.ok(Math.ceil(VERIFY_MS / VERIFY_STEP_MS) >= 8 && VERIFY_MS <= 3000, "a 2–3 s window, sampled");
r = rig([{ muted: false, level: null }]);
assert.equal(await r.dev.revive(), true);
assert.deepEqual(r.calls, ["adopt"], "a browser that does not report a level trusts a live unmuted track");

// ══ 5 · the mic analyser listens to ONE capture ══════════════════════════════════════════════════════════════
globalThis.MediaStream = class {};
const live = new Set();
class Node { connect(to) { if (to && to.isMicAn) live.add(this); } disconnect() { live.delete(this); } }
globalThis.window.AudioContext = class { constructor() { this.state = "running"; }
  createAnalyser() { const a = new Node(); a.isMicAn = true; return a; }
  createMediaStreamSource() { return new Node(); } close() {} };
const audio = await import("../../../../frontend/app/services/audio.js?v=2");
audio.initMic(new MediaStream());
audio.rebindMic(new MediaStream());
audio.rebindMic(new MediaStream());
assert.equal(live.size, 1, "a rebind replaces the source: stacked captures make the orb move over a deaf wire");
audio.reset("test");

// ══ 6 · a republish keeps the track and publishes it anew ════════════════════════════════════════════════════
const ops = []; const pubTrack = { mediaStreamTrack: new FakeTrack("cap") };
const room = { localParticipant: {
  audioTrackPublications: new Map([["a", { track: pubTrack }]]),
  unpublishTrack: async (tr, stop) => ops.push(["unpublish", tr === pubTrack, stop]),
  publishTrack: async (lt) => ops.push(["publish", lt.t.label]) } };
await republishMic({ room, track: pubTrack.mediaStreamTrack, closed: false, wrap: (t) => ({ t }) });
assert.deepEqual(ops, [["unpublish", true, false], ["publish", "cap"]], "unpublish without stopping, then publish");

console.log("ok — an interruption waits, a revive is proved, the analyser hears one capture");
