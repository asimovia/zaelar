// ============================================================================
// test_a_device_problem_turns_its_icon_red.mjs — V2-788, node 3.119.
//
// THE INCIDENT. Mid-session the agent's voice stopped being heard in the browser while the engine kept
// synthesising it. The browser had reported «TrackSubscribed», «estado tras attach», «play() OK» at connect time
// and NOTHING afterwards: a paused element, a dead remote track, an interrupted audio context, a lost output
// device and a blocked playback all looked identical — silence in the log and a blue icon on the orb.
//
// This drives the REAL `services/device-health.js` over the REAL `core/store.js` with fake tracks, a fake <audio>
// element, a fake permission status and a fake device list, and checks the contract on both devices:
//   • a problem condition turns the derived health to problem (what paints the icon red) AND reports a
//     `client` event through POST /api/client-log naming the device and the condition;
//   • clearing the condition restores the health by itself, and reports the clear;
//   • a deliberate user mute is never red — except a revoked permission, which no mute explains;
//   • nothing is reported twice for the same state (on change, not periodically).
//
// Run: node tests/browser/unit/voice/test_a_device_problem_turns_its_icon_red.mjs
// ============================================================================
import assert from "node:assert/strict";

const mem = new Map([["hb_lang", "en"]]);
globalThis.localStorage = { getItem: k => (mem.has(k) ? mem.get(k) : null),
                            setItem: (k, v) => mem.set(k, String(v)), removeItem: k => mem.delete(k) };
const posts = [];
globalThis.fetch = async (url, opts = {}) => {
  if (url === "/api/client-log") posts.push(JSON.parse(opts.body));
  return { ok: true, json: async () => ({}), text: async () => "" };
};
globalThis.document = { documentElement: { lang: "en", setAttribute(){}, style: { setProperty(){} } },
                        querySelectorAll: () => [], querySelector: () => null, addEventListener(){} };
globalThis.window = { addEventListener(){}, location: { href: "http://localhost/" } };

const store = await import("../../../../frontend/app/core/store.js?v=2");
const health = await import("../../../../frontend/app/services/device-health.js?v=1");

class FakeTrack extends EventTarget {
  constructor(label) { super(); this.label = label; this.muted = false; this.enabled = true; }
  fire(type) { if (type === "mute") this.muted = true; if (type === "unmute") this.muted = false; this.dispatchEvent(new Event(type)); }
}
class FakeAudio extends EventTarget {
  constructor() { super(); this.srcObject = null; this.sinkId = ""; this.error = null; }
  fire(type) { this.dispatchEvent(new Event(type)); }
}
const reports = (device, state) => posts.filter(p => p.device === device && p.state === state).length;
const red = (device) => !store.deviceHealth(device).ok;

store.setStarted(true);
store.setMicMuted(false);
store.setBotMuted(false);

// ══ 1 · MICROPHONE: a dead track is red, reported, and a new track clears it ═══════════════════════════════
const mic1 = new FakeTrack("Built-in Microphone");
health.watchMicTrack(mic1);
assert.equal(red("mic"), false, "a fresh live track is healthy");
mic1.fire("ended");
assert.equal(red("mic"), true, "an ended mic track must turn the mic red");
assert.equal(store.micHealth().reason, "track_ended");
assert.equal(reports("mic", "problem:track_ended"), 1, "the problem must be reported as a client event");
health.watchMicTrack(new FakeTrack("Built-in Microphone"));
assert.equal(red("mic"), false, "the restarted capture clears the red by itself");
assert.equal(reports("mic", "clear:track_ended"), 1, "and the clear is reported too");

// The source going silent (OS switch / another app took the device) is red; its unmute clears it.
const mic2 = new FakeTrack("USB Mic");
health.watchMicTrack(mic2);
mic2.fire("mute");
assert.equal(store.micHealth().reason, "track_muted");
mic2.fire("mute");
assert.equal(reports("mic", "problem:track_muted"), 1, "the same state is never reported twice");
mic2.fire("unmute");
assert.equal(red("mic"), false);

// ══ 2 · A DELIBERATE MIC MUTE IS NOT RED — a revoked permission is ═════════════════════════════════════════
mic2.fire("mute");
store.setMicMuted(true);
assert.equal(red("mic"), false, "the operator muted the mic on purpose: a silent source is not a fault then");
store.setMicMuted(false);
assert.equal(red("mic"), true, "…and the fault is still there the moment he unmutes");
mic2.fire("unmute");

const perm = Object.assign(new EventTarget(), { state: "granted" });
await health.watchMicPermission({ permissions: { query: async () => perm } });
assert.equal(red("mic"), false);
perm.state = "denied"; perm.dispatchEvent(new Event("change"));
assert.equal(store.micHealth().reason, "permission_denied", "a revocation mid-session is caught by onchange");
assert.equal(reports("mic", "problem:permission_denied"), 1);
store.setMicMuted(true);
assert.equal(red("mic"), true, "no mute explains a revoked permission");
store.setMicMuted(false);
perm.state = "granted"; perm.dispatchEvent(new Event("change"));
assert.equal(red("mic"), false, "granting it back clears the red");

// getUserMedia failing because another application holds the device.
health.micCaptureResult(Object.assign(new Error("Could not start audio source"), { name: "NotReadableError" }));
assert.equal(store.micHealth().reason, "capture_error");
health.micCaptureResult(null);
assert.equal(red("mic"), false);

// ══ 3 · SPEAKER: paused element / dead remote track / blocked playback ═════════════════════════════════════
const el = new FakeAudio();
health.watchBotElement(el);
el.srcObject = {};
el.fire("pause");
assert.equal(store.spkHealth().reason, "paused", "a paused bot element mid-session must turn the speaker red");
assert.equal(reports("spk", "problem:paused"), 1);
el.fire("playing");
assert.equal(red("spk"), false, "playing again clears it");
el.fire("waiting");
assert.equal(red("spk"), false, "buffering is reported, not painted");
assert.ok(posts.some(p => p.device === "spk" && p.state === "element:waiting"), "…but it IS reported");

// stop() pauses the element on purpose and drops srcObject: that is not a fault.
el.srcObject = null;
el.fire("pause");
assert.equal(red("spk"), false, "the session's own teardown pause is not red");

const remote = new FakeTrack("agent");
health.watchRemoteTrack(remote);
remote.fire("ended");
assert.equal(store.spkHealth().reason, "track_ended");
health.watchRemoteTrack(new FakeTrack("agent"));
assert.equal(red("spk"), false, "a new remote track clears it");

// A remote track flagged muted between utterances is silence, not a fault; while speaking it is one.
const remote2 = new FakeTrack("agent");
health.watchRemoteTrack(remote2);
remote2.fire("mute");
store.setBotSpeaking(false);
assert.equal(red("spk"), false, "no media between utterances is normal");
store.setBotSpeaking(true);
assert.equal(store.spkHealth().reason, "remote_muted", "no media while the agent speaks is the fault");
remote2.fire("unmute");
store.setBotSpeaking(false);

store.setAudioBlocked(true);
assert.equal(store.spkHealth().reason, "blocked", "the SDK's own blocked verdict is the speaker's health");
store.setAudioBlocked(false);
assert.equal(red("spk"), false);

// ══ 4 · SILENT WHILE SPEAKING — the «I can't hear it» signature ════════════════════════════════════════════
let now = 1_000_000;
store.setBotSpeaking(true);
for (let i = 0; i <= health.SILENCE_MS / 250; i++, now += 250) health.tickSilence({ now, level: 0, ctxState: "running" });
assert.equal(store.spkHealth().reason, "silent_while_speaking", "speaking with no received energy must go red");
assert.equal(reports("spk", "problem:silent_while_speaking"), 1, "reported once, not on every tick");
health.tickSilence({ now: now += 250, level: 0.2, ctxState: "running" });
assert.equal(red("spk"), false, "energy coming back clears it");
// An analyser context that is not running reads zeros: it must not judge.
for (let i = 0; i <= 2 * health.SILENCE_MS / 250; i++, now += 250) health.tickSilence({ now, level: 0, ctxState: "suspended" });
assert.equal(red("spk"), false, "no verdict from a suspended analyser");
// Short pauses inside speech do not trip it.
for (let i = 0; i < 4; i++, now += 250) health.tickSilence({ now, level: 0, ctxState: "running" });
assert.equal(red("spk"), false);
store.setBotSpeaking(false);

// ══ 5 · A DELIBERATE SPEAKER MUTE IS NOT RED ═══════════════════════════════════════════════════════════════
store.setBotMuted(true);
store.setAudioBlocked(true);
el.srcObject = {}; el.fire("pause");
store.setBotSpeaking(true);
for (let i = 0; i <= health.SILENCE_MS / 250; i++, now += 250) health.tickSilence({ now, level: 0, ctxState: "running" });
assert.equal(red("spk"), false, "the operator muted the speaker on purpose: nothing about it is red");
store.setBotMuted(false);
assert.equal(red("spk"), true, "…and the real faults show the moment he unmutes");
store.setAudioBlocked(false); el.fire("playing"); store.setBotSpeaking(false);
assert.equal(red("spk"), false);

// ══ 6 · OUTPUT DEVICES: the list that had outputs and lost them ════════════════════════════════════════════
const devs = [{ kind: "audioinput", deviceId: "a" }, { kind: "audiooutput", deviceId: "default", label: "Speakers" }];
const nav = { mediaDevices: { enumerateDevices: async () => devs } };
await health.checkDevices(nav);
assert.equal(red("spk"), false);
devs.splice(1, 1);
await health.checkDevices(nav);
assert.equal(store.spkHealth().reason, "no_output", "every output gone means sound is going nowhere");
devs.push({ kind: "audiooutput", deviceId: "default", label: "Headphones" });
await health.checkDevices(nav);
assert.equal(red("spk"), false);
assert.ok(posts.some(p => p.state === "default_output:Headphones"), "a change of default output is reported");

// ══ 7 · A STOPPED SESSION IS NOT A BROKEN DEVICE ═══════════════════════════════════════════════════════════
const mic3 = new FakeTrack("m"); health.watchMicTrack(mic3); mic3.fire("ended");
assert.equal(red("mic"), true);
health.clearSession();
assert.equal(red("mic"), false, "stop() takes session-scoped conditions with it");

console.log("ok — device health: red on problem, reported, clears by itself, a deliberate mute is not red");
