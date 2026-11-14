// V2-900 — the gym card's half: every screen paints from real view data, one screen drives the session.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "../../../..");
const W = join(ROOT, "widgets/gym");

function fakeDom() {
  const mk = (tag) => {
    const e = { tag, children: [], className: "", _text: "", style: {}, dataset: {}, attrs: {}, isConnected: true,
      classList: { add(c) { e.className += " " + c; }, toggle() {}, contains(c) { return e.className.split(" ").includes(c); } },
      appendChild(c) { e.children.push(c); c.parent = e; return c; }, remove() {},
      setAttribute(k, v) { e.attrs[k] = v; }, getAttribute(k) { return e.attrs[k]; } };
    Object.defineProperty(e, "textContent", { get() { return e._text + e.children.map((c) => c.textContent || "").join(" "); },
      set(v) { e._text = String(v); e.children = []; } });
    return e;
  };
  globalThis.document = { getElementById: () => null, createElement: mk, createElementNS: (_, t) => mk(t), head: mk("head") };
  globalThis.window = globalThis;
}
fakeDom();
const tick = (ms = 0) => new Promise((r) => setTimeout(r, ms));
const find = (e, pred, out = []) => { if (pred(e)) out.push(e); for (const c of e.children || []) find(c, pred, out); return out; };

const { scoreHue } = await import(join(W, "js/home.js"));
if (process.argv[2] === "colours") {
  // the original app's thresholds: opportunity ≥5/4 red, 3 orange, ≥1 amber, 0 green (optimal), ≥−3 grey, below blue;
  // building ≥3 green, ≥1 teal, 0 grey, ≥−2 amber, −3 orange, below red.
  const opp = [5, 4, 3, 1, 0, -3, -5].map((s) => scoreHue(s, "opportunity"));
  assert.deepEqual(opp, ["red", "red", "orange", "amber", "green", "grey", "blue"]);
  const bld = [5, 3, 1, 0, -1, -3, -5].map((s) => scoreHue(s, "building"));
  assert.deepEqual(bld, ["green", "green", "teal", "grey", "amber", "orange", "red"]);
  console.log("colours ok"); process.exit(0);
}

const V = JSON.parse(readFileSync(process.argv[3], "utf-8"));
let beeps = 0;
globalThis.AudioContext = class { constructor() { beeps++; this.currentTime = 0; this.destination = {}; }
  createOscillator() { return { connect() {}, start() {}, stop() {}, frequency: {} }; }
  createGain() { return { connect() {}, gain: { setValueAtTime() {}, linearRampToValueAtTime() {} } }; } close() {} };

function screen({ form = "desktop", background = false, hr = false, running = true } = {}) {
  const calls = [], states = [];
  let started = 0;
  const dev = {
    details: async () => ({ form, background_sessions: background, sensors: { heart_rate: { available: hr } } }),
    activity: async (o) => { started++; calls.push(["activity", o.sensors]); return { stop: async () => {} }; },
  };
  const ctx = { t: null, lang: "en", running, device: async () => dev, top() {},
    action: async (name, p) => { calls.push([name, p]); return { ok: true }; },
    state: async (s) => { states.push(s); } };
  return { ctx, calls, states, get started() { return started; } };
}

const m = await import(join(W, "widget.js"));
const { UI } = await import(join(W, "js/util.js"));
const broken = (el) => find(el, (e) => e.className === "hb-empty-state" && /could not be drawn/.test(e._text)).length;

// Every screen, in both languages, from the real view data.
for (const lang of ["en", "es"]) {
  const s = screen();
  s.ctx.lang = lang;
  const el = document.createElement("div");
  m.render(el, V.onboarding, s.ctx);
  assert.ok(/Choose a program/.test(el.textContent) && !broken(el), "onboarding");
  for (const view of ["home", "preview", "calendar", "muscles", "config", "planner", "program", "log"]) {
    UI.view = view; UI.arg = null;
    m.render(el, V.ready, s.ctx);
    assert.equal(broken(el), 0, view + " paints");
    assert.equal(s.states.at(-1).view, view, view + " is reported");
  }
  const sid = V.ready.sessions[0].id;
  UI.view = "summary"; UI.arg = sid;
  m.render(el, V.ready, s.ctx);
  assert.ok(/E1\)/.test(el.textContent) && /Goblet|goblet/i.test(el.textContent), "a summary lists E1 with its exercise");
  UI.view = "exercise"; UI.arg = "goblet-squat";
  m.render(el, V.ready, s.ctx);
  assert.ok(/12×20/.test(el.textContent), "an exercise's history shows its sets");
  UI.view = "home";
}

// The session, each face, and what the card reports.
{
  const s = screen();
  const el = document.createElement("div");
  for (const [k, phase, text] of [["timed", "timed", /Block 1 \/ 15/], ["exercise", "exercise", /Set 1 of 4/],
    ["alternative", "exercise", /Barbell bench press/], ["rest", "rest", /150/], ["finished", "finished", /Session complete/]]) {
    m.render(el, V[k], s.ctx);
    assert.equal(broken(el), 0, k + " paints");
    assert.ok(text.test(el.textContent), k + " shows " + text);
    const st = s.states.at(-1);
    assert.equal(st.view, "session"); assert.equal(st.phase, phase, k + " phase");
  }
  assert.equal(s.states.find((x) => x.phase === "exercise").exercise, "Dumbbell bench press");
  assert.ok(/40/.test(JSON.stringify(V.rest.age)) && /threshold/.test(
    (() => { m.render(el, V.rest, s.ctx); return el.textContent; })()), "an age gives the heart rate its zone");
}

// One screen drives: a desktop that did not start the session never claims it; the phone app does.
{
  const desk = screen({ form: "desktop" });
  m.render(document.createElement("div"), V.exercise, desk.ctx);
  await tick(); await tick();
  assert.equal(desk.calls.filter((c) => c[0] === "claim").length, 0, "a desktop never claims what it did not start");
  assert.equal(desk.started, 0);
  const phone = screen({ form: "phone", hr: true });
  m.render(document.createElement("div"), V.exercise, phone.ctx);
  await tick(); await tick();
  const claim = phone.calls.find((c) => c[0] === "claim");
  assert.ok(claim, "the phone claims the session");
  // Now it owns it: the strap starts, and a change of block beeps — only here, and not with the agent stopped.
  const owned = (d, cue) => ({ ...d, live: { ...d.live, owner: claim[1].owner, cue } });
  const el = document.createElement("div");
  m.render(el, owned(V.exercise, 5), phone.ctx);
  await tick(); await tick();
  assert.equal(phone.started, 1, "the driving screen reads the strap");
  assert.deepEqual(phone.calls.find((c) => c[0] === "activity")[1], ["heart_rate"]);
  const b0 = beeps;
  m.render(el, owned(V.exercise, 6), phone.ctx);
  await tick(); await tick();
  assert.equal(beeps, b0 + 1, "a new cue beeps on the driving screen");
  phone.ctx.running = false;
  m.render(el, owned(V.exercise, 7), phone.ctx);
  await tick(); await tick();
  assert.equal(beeps, b0 + 1, "no beep with the agent stopped");
  const other = screen({ form: "desktop" });
  const m2 = await import(join(W, "widget.js") + "?other");           // another browser: its own module, its own token
  m2.render(document.createElement("div"), owned(V.exercise, 8), other.ctx);
  await tick(); await tick();
  assert.equal(beeps, b0 + 1, "a screen that does not drive never beeps");
}

// A timer that ran out is reported once, by whichever screen sees it.
{
  const s = screen();
  const el = document.createElement("div");
  m.render(el, V.timed_expired, s.ctx);
  await tick(600);
  const done = s.calls.filter((c) => c[0] === "timer_done");
  assert.equal(done.length, 1, "reported once");
  assert.deepEqual(done[0][1], { i: 0, set: 0, resting: false });
  el.isConnected = false;
  await tick(300);
}
console.log("screens ok");
process.exit(0);
