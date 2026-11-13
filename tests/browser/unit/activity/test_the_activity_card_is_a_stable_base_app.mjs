// V2-898 — the activity card as a stable base app: a screen whose sensors fail never holds the activity; a failure is
// per activity, not forever; an activity that ends while its sensors start stops them; a reload of the same tab is
// still the recorder; numbers read as the person's language writes them; a stored activity opens from its row; the
// 7-day bars and the heart-rate sparkline come only from stored data; the strap in use is shown.
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "../../../..");

function fakeDom() {
  const mk = (tag) => ({ tag, children: [], className: "", _text: "", style: {}, isConnected: true, attrs: {},
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(" "); },
    set textContent(v) { this._text = v == null ? "" : String(v); this.children = []; },
    appendChild(c) { this.children.push(c); return c; }, setAttribute(k, v) { this.attrs[k] = v; },
    set onclick(f) { this._click = f; }, get onclick() { return this._click; },
    get firstChild() { return this.children[0] || { textContent: "" }; } });
  globalThis.document = { getElementById: () => ({}), createElement: mk, createElementNS: (_, t) => mk(t), head: mk("head") };
  const store = {};
  globalThis.sessionStorage = { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = String(v); } };
  globalThis.localStorage = { getItem: (k) => store["L" + k] ?? null, setItem: (k, v) => { store["L" + k] = String(v); } };
}
fakeDom();
const tick = async (n = 4) => { for (let i = 0; i < n; i++) await new Promise((r) => setTimeout(r, 0)); };
const all = (el, pred, out = []) => { if (pred(el)) out.push(el); (el.children || []).forEach((c) => all(c, pred, out)); return out; };

function screen({ background = false, fail = "", sensors = { location: { available: true } }, delay = 0, lang = "en" } = {}) {
  const calls = [];
  let started = 0, stopped = 0;
  const dev = {
    details: async () => ({ platform: background ? "ios" : "web", background_sessions: background, sensors }),
    activity: async () => {
      started++; calls.push(["activity"]);
      if (delay) await new Promise((r) => setTimeout(r, delay));
      return fail ? { error: fail } : { background, stop: async () => { stopped++; } };
    },
  };
  const ctx = { t: null, lang, device: async () => dev, state: async () => {},
    action: async (name, p) => { calls.push([name, p]); return { ok: true }; } };
  return { ctx, calls, get started() { return started; }, get stopped() { return stopped; } };
}
const load = (tag) => import(join(ROOT, "widgets/activity/widget.js") + "?" + tag);

// A tapped screen whose sensors fail never claims (the phone can still take the activity), and says why in words.
{
  const m = await load("fail");
  const s = screen({ fail: "denied" });
  const el = document.createElement("div");
  m.render(el, { status: "idle", history: [] }, s.ctx);
  all(el, (e) => e.className === "ac-btn")[0].onclick();
  m.render(el, { status: "running", kind: "cycling", owner: null, started_at: 1, route: [] }, s.ctx);
  await tick();
  assert.equal(s.calls.filter((c) => c[0] === "claim").length, 0, "a screen that reads nothing claimed the activity");
  assert.match(el.textContent, /permission denied/, "the failure is said in words");
  m.render(el, { status: "running", kind: "cycling", owner: null, started_at: 1, route: [], elapsed_s: 5 }, s.ctx);   // the next push
  await tick();
  assert.equal(s.started, 1, "a failed start is retried on every push of the same activity (a permission prompt each time)");
  // A NEW activity tapped on the same screen is tried again — the failure belonged to the last one.
  m.render(el, { status: "idle", history: [] }, s.ctx);
  all(el, (e) => e.className === "ac-btn")[0].onclick();
  m.render(el, { status: "running", kind: "cycling", owner: null, started_at: 2, route: [] }, s.ctx);
  await tick();
  assert.equal(s.started, 2, "a failure for one activity blocked the next one");
}

// An activity that ends while the sensors are still starting stops them — no session left reading for nothing.
{
  const m = await load("ended");
  const s = screen({ background: true, delay: 20 });
  const el = document.createElement("div");
  m.render(el, { status: "running", kind: "running", owner: null, started_at: 5, route: [] }, s.ctx);
  await tick();
  m.render(el, { status: "idle", history: [] }, s.ctx);
  await new Promise((r) => setTimeout(r, 40));
  assert.equal(s.stopped, 1, "the session that started after the stop kept reading");
  assert.equal(s.calls.filter((c) => c[0] === "claim").length, 0);
}

// The same tab reloaded is still the screen that owns its activity: it resumes instead of orphaning it.
{
  const a = await load("reload-a");
  const sa = screen();
  const el = document.createElement("div");
  a.render(el, { status: "idle", history: [] }, sa.ctx);
  all(el, (e) => e.className === "ac-btn")[0].onclick();
  a.render(el, { status: "running", kind: "walking", owner: null, started_at: 9, route: [] }, sa.ctx);
  await tick();
  const owner = sa.calls.find((c) => c[0] === "claim")[1].owner;
  const b = await load("reload-b");                        // a fresh module = the page reloaded
  const sb = screen();
  b.render(document.createElement("div"), { status: "running", kind: "walking", owner, started_at: 9, route: [] }, sb.ctx);
  await tick();
  assert.equal(sb.started, 1, "the reloaded tab no longer recognised its own activity");
}

// Numbers as the person's language writes them; a reading we lack is «—», never a zero.
{
  const m = await load("es");
  const s = screen({ lang: "es" });
  const el = document.createElement("div");
  m.render(el, { status: "running", kind: "cycling", owner: "someone-else", started_at: 3, route: [], has_location: true,
    distance_m: 12400, speed_kmh: 21.5, climb_m: null, heart_rate: null, has_heart_rate: false }, s.ctx);
  const t = el.textContent;
  assert.match(t, /12,40 km/, "distance not in the person's locale: " + t);
  assert.match(t, /21,5 km\/h/);
  assert.doesNotMatch(t, /\b0 m\b/, "no barometer drew a zero climb");
}

// Live heart-rate sparkline only with readings; none drawn without them.
{
  const m = await load("spark");
  const s = screen();
  const el = document.createElement("div");
  const base = { status: "running", kind: "running", owner: "x", started_at: 4, route: [] };
  m.render(el, { ...base, hr_recent: [[1000, 120]] }, s.ctx);
  assert.equal(all(el, (e) => e.attrs && e.attrs.class === "ac-spark").length, 0, "a sparkline drawn from one reading");
  m.render(el, { ...base, heart_rate: 140, hr_recent: [[1000, 120], [2000, 130], [3000, 140]] }, s.ctx);
  assert.equal(all(el, (e) => e.attrs && e.attrs.class === "ac-spark").length, 1, "no sparkline with readings");
}

// At rest: 7-day bars from the stored summaries, a row opens its summary, a summary without GPS says «—».
{
  const m = await load("hist");
  const s = screen();
  const el = document.createElement("div");
  const now = Date.now();
  const history = [
    { kind: "running", label: "", started_at: now - 3600e3, elapsed_s: 1800, distance_m: 5200, avg_speed_kmh: 10.4, hr_avg: 150, hr_max: 171, climb_m: 40 },
    { kind: "driving", label: "", started_at: now - 2 * 86400e3, elapsed_s: 600, distance_m: null, avg_speed_kmh: null, hr_avg: null, hr_max: null, climb_m: null },
  ];
  m.render(el, { status: "idle", history, days: [[history[0].started_at, 5200]] }, s.ctx);
  assert.equal(all(el, (e) => e.className === "ac-week").length, 1, "no 7-day bars from the stored summaries");
  assert.match(el.textContent, /Last 7 days · 5\.2 km/);
  const rows = all(el, (e) => e.className === "ac-row");
  assert.equal(rows.length, 2);
  assert.match(rows[1].textContent, /—/, "a drive with no GPS printed a distance");
  assert.doesNotMatch(rows[1].textContent, /0\.0 km/);
  rows[0].onclick();
  assert.equal(all(el, (e) => e.className === "ac-detail").length, 1, "a tap on a row did not open its summary");
  assert.match(el.textContent, /171/, "the summary's max heart rate is not shown");
  m.render(el, { status: "idle", history: [], days: [] }, s.ctx);
  assert.equal(all(el, (e) => e.className === "ac-week").length, 0, "bars drawn with no data");
}

// The strap in use is a visible setting: its name and «Change» where a strap can be read; nothing where it cannot.
{
  const m = await load("strap");
  localStorage.setItem("hb-activity-strap", "Polar H10");
  const s = screen({ sensors: { location: { available: true }, heart_rate: { available: true, saved_strap: true } } });
  const el = document.createElement("div");
  m.render(el, { status: "idle", history: [] }, s.ctx);
  await tick();
  assert.match(el.textContent, /Heart rate from Polar H10/);
  assert.match(el.textContent, /Change/);
  const d = await load("strap-desk");
  const el2 = document.createElement("div");
  d.render(el2, { status: "idle", history: [] }, screen({ sensors: {} }).ctx);
  await tick();
  assert.doesNotMatch(el2.textContent, /Heart rate from|Change/, "a strap row on a screen with no strap sensor");
  assert.match(el2.textContent, /no location or heart-rate sensor/, "a screen that cannot record does not say so");
}
console.log("ok");
process.exit(0);   // the card's 1 s clock and 5 s flush intervals would keep node alive
