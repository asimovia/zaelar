// V2-870 P2 — the screen as a sensor: one door (services/device.js), the native plugin when the app runs it, the Web
// API otherwise, and every failure a value (never a throw), so a declined permission breaks no app.
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "../../../..");
const d = await import(join(ROOT, "frontend/app/services/device.js"));

// A browser with no geolocation: the door says so instead of throwing.
delete globalThis.Capacitor;
assert.deepEqual(await d.location(), { error: "unsupported" }, "no geolocation → unsupported, as a value");
assert.ok(!d.capabilities().includes("location"), "a screen without geolocation does not claim it");

// The native app: the Capacitor plugin answers, and its position is mapped to the door's shape.
const cleared = [];
let watcher = null;
const pos = { coords: { latitude: 41.39, longitude: 2.17, accuracy: 8, altitude: null, heading: null, speed: 1.2 }, timestamp: 42 };
globalThis.Capacitor = {
  isNativePlatform: () => true,
  Plugins: { Geolocation: {
    getCurrentPosition: async (o) => { assert.equal(o.enableHighAccuracy, true); return pos; },
    watchPosition: (o, cb) => { watcher = cb; return Promise.resolve("w1"); },
    clearWatch: async ({ id }) => { cleared.push(id); },
  } },
};
assert.ok(d.capabilities().includes("location"), "the app's plugin makes location available");
assert.deepEqual(await d.location(),
  { lat: 41.39, lon: 2.17, accuracy: 8, altitude: null, heading: null, speed: 1.2, at: 42 }, "a fix in the door's shape");

const seen = [];
const stop = d.watchLocation((f) => seen.push(f));
watcher(pos, null);
watcher(null, { message: "Location permission was denied" });
assert.equal(seen[0].lat, 41.39, "each fix reaches the app");
assert.deepEqual(seen[1], { error: "denied" }, "a refusal while watching is a value too");
stop();
await new Promise((r) => setTimeout(r, 0));
assert.deepEqual(cleared, ["w1"], "stop() clears the native watch by its id");

// A refusal on a single read.
globalThis.Capacitor.Plugins.Geolocation.getCurrentPosition = async () => { throw new Error("User denied location permission"); };
assert.deepEqual(await d.location(), { error: "denied" });
globalThis.Capacitor.Plugins.Geolocation.getCurrentPosition = async () => { throw { code: 3, message: "Timeout expired" }; };
assert.deepEqual(await d.location(), { error: "timeout" });

// A page that merely has a Capacitor object but is not the native app uses the Web API, not the plugin.
globalThis.Capacitor = { isNativePlatform: () => false, Plugins: { Geolocation: { getCurrentPosition: async () => pos } } };
assert.deepEqual(await d.location(), { error: "unsupported" }, "the plugin is only trusted inside the native app");

console.log("ok");
