// V2-890 — an activity the person starts: in the native app the `ZaelarDevice` plugin reads natively (screen locked
// included) and the door hands the missed samples over when the screen comes back, each sample exactly once; in a
// browser only location runs, foreground; with no sensor at all the answer is a value.
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "../../../..");
const d = await import(join(ROOT, "frontend/app/services/device.js"));

let vis = "visible";
const docListeners = {};
globalThis.document = { get visibilityState() { return vis; },
  addEventListener: (k, f) => { docListeners[k] = f; }, removeEventListener: (k) => { delete docListeners[k]; } };

// A browser: details() says web/foreground; activity without location is unsupported.
delete globalThis.Capacitor;
const web = await d.details();
assert.equal(web.platform, "web");
assert.equal(web.background_sessions, false, "a browser never claims the locked-screen session");
assert.deepEqual(await d.activity({ sensors: ["heart_rate"] }), { error: "unsupported" }, "no strap in a browser, as a value");
assert.deepEqual((await d.heartRateStraps()).error, "unsupported");

// The native app.
const buffer = [];
let started = null, stopped = false, live = null;
const plugin = {
  capabilities: async () => ({ platform: "ios", form: "phone", background_sessions: true,
    sensors: { heart_rate: { available: true, permission: "granted" } } }),
  startSession: async (o) => { started = o; return { session: { id: "s1" } }; },
  stopSession: async () => { stopped = true; },
  addListener: async (name, f) => { assert.equal(name, "sample"); live = f; return { remove() { live = null; } }; },
  drain: async ({ after }) => ({ samples: buffer.filter((s) => s.seq > after), more: false }),
  scanHeartRate: async (o) => (o.pick ? { saved: o.pick } : { straps: [{ id: "H10", name: "Polar H10" }] }),
};
globalThis.Capacitor = { isNativePlatform: () => true, Plugins: { ZaelarDevice: plugin } };
assert.equal((await d.details()).platform, "ios", "the app's plugin answers what this phone has");

const got = [];
const a = await d.activity({ sensors: ["location", "heart_rate"], label: "ride", kind: "cycling" }, (s) => got.push(s.seq));
assert.equal(a.background, true);
assert.deepEqual(started.sensors, ["location", "heart_rate"]);
assert.equal(started.background, true, "the native session keeps reading with the screen locked");

// Awake: a live sample arrives through the event and is also in the native buffer.
const s1 = { seq: 1, kind: "heart_rate", bpm: 120 };
buffer.push(s1); live(s1);
// Locked: the WebView is frozen, the native side keeps buffering.
vis = "hidden";
buffer.push({ seq: 2, kind: "location", lat: 1, lon: 2 }, { seq: 3, kind: "heart_rate", bpm: 131 });
// Back: the door drains what was missed.
vis = "visible"; docListeners.visibilitychange();
await new Promise((r) => setTimeout(r, 0));
assert.deepEqual(got, [1, 2, 3], "every sample reaches the app once, the locked ones on return");

await a.stop();
assert.equal(stopped, true, "stop() ends the native session");
assert.equal(live, null, "and drops the listener");

const straps = await d.heartRateStraps();
assert.deepEqual(straps.straps, [{ id: "H10", name: "Polar H10" }]);
assert.deepEqual(await straps.pick("H10"), { saved: "H10" });

// A refusal is a value.
plugin.startSession = async () => { throw new Error("Location permission was denied"); };
assert.deepEqual(await d.activity({ sensors: ["location"] }), { error: "denied" });
console.log("ok");
