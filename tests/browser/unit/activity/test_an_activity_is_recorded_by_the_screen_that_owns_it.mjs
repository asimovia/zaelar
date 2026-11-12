// V2-890 F1 — the card's half: the phone app claims an activity started by voice; a desktop browser does not (it
// only reflects), unless he tapped Start there; an ended activity stops the sensors.
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "../../../..");

function fakeDom() {
  const mk = (tag) => ({ tag, children: [], className: "", textContent: "", style: {}, isConnected: true,
    appendChild(c) { this.children.push(c); return c; }, setAttribute() {}, set onclick(f) { this._click = f; }, get onclick() { return this._click; },
    get firstChild() { return this.children[0] || { textContent: "" }; } });
  globalThis.document = { getElementById: () => ({}), createElement: mk, createElementNS: (_, t) => mk(t), head: mk("head") };
}
fakeDom();
const tick = () => new Promise((r) => setTimeout(r, 0));

function screen(background) {
  const calls = [];
  let started = 0, stopped = 0;
  const dev = {
    details: async () => ({ platform: background ? "ios" : "web", background_sessions: background,
      sensors: { location: { available: true }, heart_rate: { available: background } } }),
    activity: async (o) => { started++; calls.push(["activity", o.sensors]); return { background, stop: async () => { stopped++; } }; },
  };
  const ctx = { t: null, lang: "en", device: async () => dev,
    action: async (name, p) => { calls.push([name, p]); return { ok: true }; } };
  return { ctx, calls, get started() { return started; }, get stopped() { return stopped; } };
}

// The desktop browser: a ride started by voice elsewhere is only reflected — no claim, no sensors.
{
  const m = await import(join(ROOT, "widgets/activity/widget.js") + "?desk");
  const s = screen(false);
  m.render(document.createElement("div"), { status: "running", kind: "cycling", owner: null, route: [] }, s.ctx);
  await tick(); await tick();
  assert.equal(s.calls.filter((c) => c[0] === "claim").length, 0, "a desktop never claims what it did not start");
  assert.equal(s.started, 0);
}

// The phone app: the same voice-started ride is claimed and the sensors start; ending it stops them.
{
  const m = await import(join(ROOT, "widgets/activity/widget.js") + "?phone");
  const s = screen(true);
  const el = document.createElement("div");
  m.render(el, { status: "running", kind: "cycling", owner: null, route: [] }, s.ctx);
  await tick(); await tick(); await tick();
  assert.ok(s.calls.some((c) => c[0] === "claim"), "the phone app claims the activity");
  assert.equal(s.started, 1, "and starts reading");
  assert.deepEqual(s.calls.find((c) => c[0] === "activity")[1], ["location", "heart_rate"], "only what this device has");
  m.render(el, { status: "idle", history: [] }, s.ctx);
  await tick(); await tick();
  assert.equal(s.stopped, 1, "an ended activity stops the sensors");
}

// The desktop where he TAPPED Start: it claims.
{
  const m = await import(join(ROOT, "widgets/activity/widget.js") + "?tap");
  const s = screen(false);
  const el = document.createElement("div");
  m.render(el, { status: "idle", history: [] }, s.ctx);
  const kinds = el.children.find((c) => c.className === "ac-kinds");
  kinds.children[0].onclick();
  m.render(el, { status: "running", kind: "cycling", owner: null, route: [] }, s.ctx);
  await tick(); await tick(); await tick();
  assert.ok(s.calls.some((c) => c[0] === "claim"), "his tap here makes this screen the recorder");
}
console.log("ok");
process.exit(0);   // the card's 1 s clock and 5 s flush intervals would keep node alive
