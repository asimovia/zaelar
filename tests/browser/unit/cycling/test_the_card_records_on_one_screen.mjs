// V2-901 — the cycling card's half: the phone app claims a voice-started ride and reads location, heart rate and
// altitude (only what the device has); a desktop browser only reflects it unless he tapped Start there; a saved ride
// stops the sensors; a view the brain pushes (ui.n) opens that ride's page through `ride_detail`; the card reports
// what it shows; the ghost's arithmetic puts each earlier attempt ahead or behind.
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "../../../..");

function fakeDom() {
  const mk = (tag) => {
    const e = { tag, children: [], className: "", style: {}, isConnected: true, attrs: {}, _t: "", value: "", disabled: false,
      classList: { add(c) { e.className += " " + c; }, remove() {}, contains: (c) => e.className.split(" ").includes(c) },
      appendChild(c) { this.children.push(c); return c; }, insertBefore(c) { this.children.unshift(c); return c; },
      setAttribute(k, v) { this.attrs[k] = v; }, querySelectorAll() { return []; }, remove() {},
      getBoundingClientRect() { return { left: 0, top: 0 }; }, setPointerCapture() {}, clientWidth: 360, clientHeight: 240,
      get firstChild() { return this.children[0] || null; }, get lastChild() { return this.children[this.children.length - 1] || { textContent: "" }; },
    };
    Object.defineProperty(e, "textContent", { get() { return e._t + e.children.map((c) => c.textContent || "").join(""); },
      set(v) { e._t = v == null ? "" : String(v); e.children = []; } });
    return e;
  };
  globalThis.document = { getElementById: () => null, createElement: mk, createElementNS: (_, t) => mk(t), head: mk("head") };
}
fakeDom();
const tick = () => new Promise((r) => setTimeout(r, 0));
const find = (n, pred) => { if (pred(n)) return n; for (const c of n.children || []) { const f = find(c, pred); if (f) return f; } return null; };

function screen(native, sensors = ["location", "heart_rate", "altitude", "motion"]) {
  const calls = [], states = [];
  let started = 0, stopped = 0;
  const avail = Object.fromEntries(sensors.map((k) => [k, { available: true }]));
  const dev = {
    details: async () => ({ platform: native ? "ios" : "web", background_sessions: native, sensors: native ? avail : { location: { available: true } } }),
    activity: async (o) => { started++; calls.push(["activity", o.sensors]); return { background: native, stop: async () => { stopped++; } }; },
  };
  const ctx = { t: null, lang: "en", device: async () => dev, top() {},
    state: async (patch) => { states.push(patch); },
    action: async (name, p) => {
      calls.push([name, p]);
      if (name === "ride_detail") return { ok: true, ride: { id: 3, name: "Coast", started_at: "2026-11-12T08:00:00Z", distance_km: 20, duration_sec: 3600 },
        route: [[41.4, 2.1, 10], [41.41, 2.1, 12]], hr: [], elevation: [], stats: null, splits: [], attempts: [], gaps: [], trackpoint_count: 2 };
      return { ok: true };
    } };
  return { ctx, calls, states, get started() { return started; }, get stopped() { return stopped; } };
}

const now = Date.now();
const running = (owner) => ({ status: "running", ui: { view: "recording", n: 1 }, segments: [], rides: [],
  current: { id: 7, owner, countdown_until_ms: now - 10_000, started_ms: now - 10_000, paused: false, elapsed_s: 10, distance_km: 0.05,
    speed_kmh: 20, avg_speed_kmh: 18, max_speed_kmh: 22, altitude_m: 12, heart_rate: null, has_heart_rate: false,
    zone: { min: 120, max: 140 }, zone_status: "idle", has_location: true, route: [], last: [41.4, 2.1], events: [],
    ghost: { inside: [], nearby: [], selected: null, approach: null, active: null, attempts: [] } } });

// The desktop browser: a ride started by voice elsewhere is only reflected — no claim, no sensors.
{
  const m = await import(join(ROOT, "widgets/cycling/widget.js") + "?desk");
  const s = screen(false);
  m.render(document.createElement("div"), running(null), s.ctx);
  await tick(); await tick();
  assert.equal(s.calls.filter((c) => c[0] === "claim").length, 0, "a desktop never claims what it did not start");
  assert.equal(s.started, 0);
  assert.deepEqual(s.states.at(-1), { phase: "running", recorder: "none", view: "recording", shown: "" });
}

// The phone app: the voice-started ride is claimed and read; saving it stops the sensors and opens the history.
{
  const m = await import(join(ROOT, "widgets/cycling/widget.js") + "?phone");
  const s = screen(true, ["location", "heart_rate", "motion"]);
  const el = document.createElement("div");
  m.render(el, running(null), s.ctx);
  await tick(); await tick(); await tick();
  assert.ok(s.calls.some((c) => c[0] === "claim"), "the phone app claims the ride");
  assert.deepEqual(s.calls.find((c) => c[0] === "activity")[1], ["location", "heart_rate"], "only what this phone has");
  m.render(el, { status: "idle", ui: { view: "history", n: 2 }, rides: [], segments: [], zone: { defaults: {} } }, s.ctx);
  await tick(); await tick();
  assert.equal(s.stopped, 1, "a saved ride stops the sensors");
  assert.equal(s.states.at(-1).view, "history");
}

// A view the brain pushes: «show me the coast ride» → ui.n moves → the card asks for that ride's page and paints it.
{
  const m = await import(join(ROOT, "widgets/cycling/widget.js") + "?push");
  const s = screen(false);
  const el = document.createElement("div");
  const base = { status: "idle", rides: [{ id: 3, name: "Coast", started_at: "2026-11-12T08:00:00Z" }], segments: [], zone: { defaults: {} } };
  m.render(el, { ...base, ui: { view: "menu", n: 4 } }, s.ctx);
  m.render(el, { ...base, ui: { view: "ride", ride: 3, n: 5 } }, s.ctx);
  await tick(); await tick(); await tick();
  assert.deepEqual(s.calls.find((c) => c[0] === "ride_detail")[1], { ride: "3" });
  assert.ok(find(el, (n) => n.tag === "h3" && n.textContent === "Coast"), "the ride's page is painted");
  assert.deepEqual(s.states.at(-1), { phase: "idle", recorder: "none", view: "ride", shown: "Coast" });
}

// The ghost's arithmetic: halfway through a 600 m segment after 60 s, a 100-s PR is 10 s ahead, a 140-s ride 10 s behind.
{
  const G = await import(join(ROOT, "widgets/cycling/js/ghost.js"));
  const g = { active: { entered_ms: 0, distance_m: 600, dist_accum: 300 }, attempts: [{ id: 1, time_sec: 100, is_pr: 1 }, { id: 2, time_sec: 140 }] };
  const r = G.competitors(g, 60_000);
  assert.deepEqual(r.map((c) => c.deltaSec), [10, -10]);
  assert.equal(G.rank(r), 2);
  assert.equal(G.nextAhead(r).id, 1); assert.equal(G.nextBehind(r).id, 2);
  assert.equal(G.progressPct(g.active), 50);
  assert.equal(G.secToFinish(g.active, 36), 30); assert.ok(G.nearFinish(g.active, 36));
  assert.equal(G.staff(r).length, 2); assert.equal(G.myY(r), 50);
}
console.log("ok");
process.exit(0);   // the card's 1 s clock and 5 s flush intervals would keep node alive
