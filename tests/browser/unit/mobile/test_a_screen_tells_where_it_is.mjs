// V2-875 — a screen tells the agent where it is only with the switch on and the permission already granted; the
// switch is the gesture that asks; flipping it writes the ENGINE's setting first.
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "../../../..");
const posts = [];
let perm = "prompt", asked = 0;
globalThis.document = { visibilityState: "visible", addEventListener() {} };
Object.defineProperty(globalThis, "navigator", { configurable: true, value: {
  permissions: { query: async () => ({ state: perm }) },
  geolocation: { getCurrentPosition: (ok) => { asked++; ok({ coords: { latitude: 41.387, longitude: 2.168, accuracy: 30 }, timestamp: 1 }); } },
} });
globalThis.localStorage = { getItem: () => null, setItem() {} };
globalThis.fetch = async (url, init) => {
  posts.push({ url, body: init && JSON.parse(init.body) });
  return { json: async () => ({ ok: true }) };
};
const tick = () => new Promise((r) => setTimeout(r, 10));
// The SAME ?v= privacy.js uses: another query string would be a second module instance (and a second timer).
const where = await import(join(ROOT, "frontend/app/services/where.js") + "?v=1");
const privacy = await import(join(ROOT, "frontend/app/services/privacy.js"));

where.setEnabled(true); await tick();
assert.equal(asked, 0, "no permission granted yet: no prompt on load, nothing reported");
assert.equal(posts.length, 0);

perm = "granted";
await where.report();
assert.equal(posts.at(-1).url, "/api/device/location");
assert.deepEqual([posts.at(-1).body.lat, posts.at(-1).body.lon], [41.387, 2.168]);

where.setEnabled(false); posts.length = 0; perm = "prompt";
assert.equal(await where.report(), null, "switch off: nothing");

privacy.loadFrom({ v2: { privacy: { location: false } } }); await tick();
assert.equal(privacy.values().location, false);
await privacy.set("location", true); await tick();
assert.deepEqual(posts[0], { url: "/api/config/v2", body: { section: "privacy", patch: { location: true } } },
  "the engine's setting is written first");
assert.ok(posts.some((p) => p.url === "/api/device/location"), "the flip is the gesture: it asks and reports");
assert.equal(privacy.values().location, true);
assert.equal(await privacy.set("camera", true), false, "only the declared switches");
where.setEnabled(false);   // the quarter-hour timer would keep the process alive
console.log("ok");
process.exit(0);           // services/api.js keeps its own timers
