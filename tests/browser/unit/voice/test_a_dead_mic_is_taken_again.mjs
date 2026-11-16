// ============================================================================
// test_a_dead_mic_is_taken_again.mjs — a capture track the SYSTEM ends is taken again; a mic nobody can use is red.
//
// THE CLASS. The system can take the microphone from a live session: iOS ends the capture track (or mutes it and never
// unmutes it) when it interrupts the audio session, a device goes away, the page is frozen in the background. The page
// painted the condition and went on publishing a dead track — the session stayed deaf until he gave up and typed.
// And when no agent ever joined the rooms the page asked for, the phone drew nothing at all.
//
// Driven over the REAL modules (`device-health.js`, `mic-device.js`, `mic-denial.js`, `core/store.js`) with fake
// tracks and injected timers:
//   • an ENDED track is lost at once; a track MUTED by its source past the grace is lost; an unmute within the grace
//     is not; a dead track found on visibility/context checks is lost;
//   • revive() takes the device again and adopts it; it is bounded per window, and his tap (force) always gets a try;
//   • `no_agent` makes the mic unusable even under his own mute, and has a translated title;
//   • the sentence that says where to allow a refused mic depends on the surface, and only the iOS app opens settings.
//
// Run: node tests/browser/unit/voice/test_a_dead_mic_is_taken_again.mjs
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
const { createMicDevice, REVIVE_MAX } = await import("../../../../frontend/app/services/mic-device.js?v=1");
const { settingsHint } = await import("../../../../frontend/app/services/mic-denial.js?v=1");
const { createMicRecover } = await import("../../../../frontend/app/services/mic-recover.js?v=1");

class FakeTrack extends EventTarget {
  constructor(label) { super(); this.label = label; this.muted = false; this.readyState = "live"; this.enabled = true; }
  fire(type) {
    if (type === "mute") this.muted = true;
    if (type === "unmute") this.muted = false;
    if (type === "ended") this.readyState = "ended";
    this.dispatchEvent(new Event(type));
  }
}
// Injected timers: `advance(ms)` runs what is due.
let clock = 0; const timers = new Map(); let nextId = 1;
const setT = (fn, ms) => { const id = nextId++; timers.set(id, { at: clock + ms, fn }); return id; };
const clearT = (id) => timers.delete(id);
const advance = (ms) => { clock += ms; for (const [id, t] of [...timers]) if (t.at <= clock) { timers.delete(id); t.fn(); } };

store.setStarted(true); store.setMicMuted(false);
const lost = [];
health.onMicLost((why) => lost.push(why));

// ══ 1 · an ENDED track is lost at once ═══════════════════════════════════════════════════════════════════════
const t1 = new FakeTrack("iPhone Microphone");
health.watchMicTrack(t1, { setT, clearT });
t1.fire("ended");
assert.deepEqual(lost, ["track_ended"], "an ended capture track must be taken again, not only painted");
assert.equal(store.micHealth().reason, "track_ended");

// ══ 2 · muted by its source past the grace → lost; unmuted within it → not ══════════════════════════════════
lost.length = 0;
const t2 = new FakeTrack("iPhone Microphone");
health.watchMicTrack(t2, { setT, clearT });
assert.equal(store.micHealth().ok, true, "a new live track clears the dead one's red");
t2.fire("mute");
advance(health.MUTE_GRACE_MS - 100);
assert.deepEqual(lost, [], "a mute is given its grace: iOS mutes for a moment and unmutes");
t2.fire("unmute");
advance(5000);
assert.deepEqual(lost, [], "an unmute inside the grace is not a loss");
t2.fire("mute");
advance(health.MUTE_GRACE_MS + 1);
assert.deepEqual(lost, ["track_muted"], "a track that stays muted by its source is lost");

// ══ 3 · a dead track found on a later look (visibility, the audio context back) is lost ══════════════════════
lost.length = 0;
const t3 = new FakeTrack("iPhone Microphone");
health.watchMicTrack(t3, { setT, clearT });
health.checkMicAlive("visible");
assert.deepEqual(lost, [], "a live track is left alone");
t3.readyState = "ended";                 // ended while the page was frozen: no event was ever delivered
health.checkMicAlive("visible");
assert.deepEqual(lost, ["visible"]);

// ══ 4 · revive() takes the device again, bounded; his tap always gets a try ════════════════════════════════
let now = 0, acquired = 0; const adopted = [];
const dev = createMicDevice({
  acquire: async () => { acquired += 1; return { getAudioTracks: () => [new FakeTrack("fresh")], getTracks: () => [] }; },
  adopt: async (s) => { adopted.push(s); },
  now: () => now,
});
for (let i = 0; i < REVIVE_MAX; i++) assert.equal(await dev.revive(), true, `revive ${i + 1} takes the device`);
assert.equal(adopted.length, REVIVE_MAX, "each revive adopts the fresh stream into the session");
assert.equal(await dev.revive(), false, "past the bound a device that keeps dying is left for his tap");
assert.equal(acquired, REVIVE_MAX, "…without asking the browser again");
assert.equal(await dev.revive(() => false, { force: true }), true, "his tap always gets one more try");
now += 61000;
assert.equal(await dev.revive(), true, "the bound is per window");
assert.equal(await dev.revive(() => true), false, "a stale session closes the fresh stream instead of adopting it");

// ══ 5 · no agent in the room: the mic is unusable, even under his own mute ═════════════════════════════════
health.setCondition("mic", "no_agent", true, "3 rooms without the agent");
assert.equal(store.micHealth().reason, "no_agent");
store.setMicMuted(true);
assert.equal(store.micHealth().ok, false, "his mute does not explain an agent that never came");
store.setMicMuted(false);
assert.equal(health.problemTitleKey("mic", "no_agent"), "orb.mic_problem_no_agent");
health.setCondition("mic", "no_agent", false, "agent joined");
health.watchMicTrack(new FakeTrack("ok"), { setT, clearT });
assert.equal(store.micHealth().ok, true);

// ══ 6 · where he allows a refused mic depends on the surface; only the iOS app opens its settings ═══════════
const docOf = (inApp, platform) => ({ documentElement: { classList: { contains: (c) => inApp && c === "in-app" },
                                                         getAttribute: (k) => (k === "data-platform" ? platform : null) } });
assert.deepEqual(settingsHint(docOf(true, "ios"), {}), { key: "voice.mic_allow_app_ios", open: "app-settings:" });
assert.deepEqual(settingsHint(docOf(true, "android"), {}), { key: "voice.mic_allow_app_android", open: "" });
assert.deepEqual(settingsHint(docOf(false, ""), { userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0)" }),
                 { key: "voice.mic_allow_ios_safari", open: "" });
assert.deepEqual(settingsHint(docOf(false, ""), { userAgent: "Mozilla/5.0 (Macintosh)" }),
                 { key: "voice.mic_allow_browser", open: "" });

// ══ 7 · the red mic's tap does what its reason needs ═══════════════════════════════════════════════════════
const calls = [];
const mk = (over = {}) => createMicRecover({
  started: () => true, start: async () => calls.push("start"), stop: async () => calls.push("stop"),
  revive: async (why, o) => { calls.push("revive:" + (o && o.force)); return true; },
  resetRetries: () => calls.push("reset"), open: (u) => calls.push("open:" + u), ...over,
});
health.setCondition("mic", "no_agent", true, "x");
await mk()("tap");
assert.deepEqual(calls, ["reset", "stop", "start"], "no agent → fresh bounds and a new room");
assert.equal(store.micHealth().ok, true, "the tap takes the red off while the new room comes");
calls.length = 0;
health.micCaptureResult({ name: "NotAllowedError", message: "denied" });
globalThis.document = { ...globalThis.document, documentElement: { ...globalThis.document.documentElement,
  classList: { contains: (c) => c === "in-app" }, getAttribute: (k) => (k === "data-platform" ? "ios" : null) } };
await mk({ probe: async () => { throw Object.assign(new Error("denied"), { name: "NotAllowedError" }); } })("tap");
assert.deepEqual(calls, ["open:app-settings:"], "a refusal the system will not ask again: the app opens its settings");
assert.equal(store.micBlocked().msg.length > 0, true, "…and says in a sentence where to allow it");
calls.length = 0;
await mk({ probe: async () => ({ getTracks: () => [] }) })("tap");
assert.deepEqual(calls, ["stop", "start"], "a permission granted now restarts the session with the mic");
assert.equal(store.micHealth().ok, true);
calls.length = 0;
health.setCondition("mic", "track_ended", true, "x");
await mk()("tap");
assert.deepEqual(calls, ["revive:true"], "a dead track: his tap takes the device again, past the bound");

console.log("ok — a dead mic is taken again; an unusable mic is red");
