// V2-899 — the nutrition card's half: it says what its face shows after every paint (V2-884), a voice `show` moves
// it once and never over his own tap, a photo goes up as a FILE through ctx.upload and the meal names it (no bytes
// in the action), every screen paints, and a model's answer is text, never markup.
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "../../../..");

function node(tag) {
  const n = {
    tag, children: [], attrs: {}, className: "", _text: "", value: "", style: { setProperty() {} }, isConnected: true,
    appendChild(c) { this.children.push(c); return c; },
    setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return this.attrs[k]; },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); },
    set textContent(v) { this._text = String(v); this.children = []; },
    set innerHTML(_) { throw new Error("innerHTML is never used"); },
  };
  return n;
}
globalThis.document = {
  _ids: new Set(), head: node("head"),
  getElementById(id) { return this._ids.has(id) ? {} : null; },
  createElement: (t) => { const n = node(t); if (t === "style") n.__style = true; return n; },
  createElementNS: (_, t) => node(t), createTextNode: (s) => ({ textContent: String(s), children: [] }),
};
const origAppend = document.head.appendChild.bind(document.head);
document.head.appendChild = (c) => { if (c.id) document._ids.add(c.id); return origAppend(c); };
globalThis.URL.createObjectURL = () => "blob:local";
globalThis.URL.revokeObjectURL = () => {};

const all = (n, out = []) => { out.push(n); for (const c of n.children || []) all(c, out); return out; };
const byClass = (el, cls) => all(el).filter((n) => (" " + (n.className || (n.attrs && n.attrs.class) || "") + " ").includes(" " + cls + " "));
const byText = (el, txt) => all(el).find((n) => n.tag === "button" && (n._text || "").includes(txt));
const tick = () => new Promise((r) => setTimeout(r, 0));

function day(date, extra) {
  return { date, kcal_in: 0, protein_g: 0, carbs_g: 0, fat_g: 0, fiber_g: 0, meals_n: 0, pending_n: 0, score: null,
    components: [], goal_status: null, weight_kg: null, rating: "gray", health_avg: null, ...(extra || {}) };
}
const TODAY = "2026-11-13";
function data(extra) {
  return { today: TODAY, profile: {}, targets: { calories: 2400, protein_g: 150, tdee: 2087 },
    days: [day("2026-11-12", { weight_kg: 79 }), day(TODAY, { kcal_in: 600, meals_n: 1, pending_n: 1, score: 40, health_avg: 4.2,
      goal_status: "low", components: ["prot"] })],
    meals: [{ id: "m1", day: TODAY, eaten_at: TODAY + "T09:00:00", description: "Eggs", status: "done", calories: 600, rating: "green", ingredients: [] },
      { id: "m2", day: TODAY, eaten_at: TODAY + "T13:00:00", source_text: "a salad", status: "pending", ingredients: [] }],
    body: [{ id: "b1", measured_at: "2026-11-12T08:00:00", weight_kg: 79 }], weight: { last: { date: "2026-11-12", weight_kg: 79 }, delta: null },
    evaluations: [], evaluating: null, coach: null, view: { screen: "today", day: null, meal: null }, estimator: { available: false },
    bin_n: 0, components_all: ["veg", "leg", "prot", "fruit", "grain", "fat", "water"], ...(extra || {}) };
}
function screen() {
  const calls = [], states = [], uploads = [];
  const ctx = { t: null, lang: "en",
    state: async (patch, o) => { states.push([patch, o]); },
    upload: async (file) => { uploads.push(file); return { name: "up_abc123_meal.jpg", url: "/widgets/nutrition/asset/up_abc123_meal.jpg" }; },
    action: async (name, p) => { calls.push([name, p]); return { ok: true, status: "failed", reason: "estimator_unavailable", meal_id: "m3" }; } };
  return { ctx, calls, states, uploads };
}

const m = await import(join(ROOT, "widgets/nutrition/widget.js"));
const { S } = await import(join(ROOT, "widgets/nutrition/js/state.js"));
// The card's clock: the logical day it calls «today» is the screen's own; pin it to the data's today.
const RealDate = Date;
globalThis.Date = class extends RealDate { constructor(...a) { super(...(a.length ? a : ["2026-11-13T12:00:00"])); } static now() { return new RealDate("2026-11-13T12:00:00").getTime(); } };

// 1. It says what it paints: today, the logical today (empty), no meal open, one meal waiting.
{
  const s = screen(), el = document.createElement("div");
  m.render(el, data(), s.ctx);
  const [patch, o] = s.states.at(-1);
  assert.deepEqual(patch, { screen: "today", day: "", meal: "", pending: 1 });
  assert.equal(o.applied, true);
  assert.ok(byClass(el, "nu-meal").length === 2, "both meals of the day are listed");
  assert.ok(el.textContent.includes("Estimating"), "a pending meal says so");
}

// 2. A voice `show` moves the card once; his tap afterwards is not undone by the next push of the same order.
{
  const s = screen(), el = document.createElement("div");
  m.render(el, data({ view: { screen: "weight", day: null, meal: null, n: 7 } }), s.ctx);
  assert.equal(s.states.at(-1)[0].screen, "weight", "the order is painted");
  assert.ok(byClass(el, "nu-chart").length === 1 || el.textContent.includes("No readings"), "the weight screen drew");
  byText(el, "Today").onclick();
  m.render(el, data({ view: { screen: "weight", day: null, meal: null, n: 7 } }), s.ctx);
  assert.equal(s.states.at(-1)[0].screen, "today", "the same order pushed again does not undo his tap");
  m.render(el, data({ view: { screen: "evaluation", day: null, meal: null, n: 8 } }), s.ctx);
  assert.equal(s.states.at(-1)[0].screen, "evaluation", "a NEW order moves it");
  m.render(el, data({ view: { screen: "today", day: "2026-11-12", meal: null, n: 9 } }), s.ctx);
  assert.deepEqual(s.states.at(-1)[0], { screen: "today", day: "2026-11-12", meal: "", pending: 0 }, "a past day is reported");
}

// 3. A photo goes up as a FILE and the meal names it; the action carries no bytes.
{
  S.screen = "today"; S.day = null; S.draft = ""; S.photo = null;
  const s = screen(), el = document.createElement("div");
  m.render(el, data(), s.ctx);
  const picker = all(el).find((n) => n.tag === "input" && n.type === "file");
  assert.equal(picker.accept, "image/*");
  assert.equal(picker.attrs.capture, "environment", "the phone opens its camera");
  picker.files = [{ name: "IMG_1.jpg", size: 200_000, type: "image/jpeg" }];
  picker.onchange();
  const ta = all(el).find((n) => n.tag === "textarea");
  S.draft = "half portion";
  await byText(el, "Save").onclick();
  await tick();
  assert.equal(s.uploads.length, 1, "the photo went through ctx.upload");
  const log = s.calls.find((c) => c[0] === "log_meal");
  assert.ok(log, "the meal was logged");
  assert.equal(log[1].photo, "up_abc123_meal.jpg");
  assert.equal(log[1].text, "half portion");
  assert.ok(!JSON.stringify(log[1]).includes("data:") && !JSON.stringify(log[1]).includes("base64"), "no bytes in the action");
  assert.equal(S.meal, "m3", "a meal with no estimate opens for him to fill");
  assert.ok(ta, "the capture has its text box");
}

// 4. Every screen paints, and a model's answer is text — markup in it never becomes an element.
{
  for (const screenName of ["weight", "coach", "evaluation", "profile"]) {
    const s = screen(), el = document.createElement("div");
    S.seenOrder = "";
    m.render(el, data({ view: { screen: screenName, n: 100 + screenName.length },
      coach: { asked_at: TODAY + "T20:00:00", recommendation: "**Starter** — <script>x</script> the salad", error: null },
      evaluations: [{ score: 72, summary: "steady", period_start: "2026-11-06", period_end: TODAY, strengths: ["protein"], issues: [],
        recommendations: [{ action: "more fibre", why: "gut", priority: 1 }] }] }), s.ctx);
    assert.equal(s.states.at(-1)[0].screen, screenName);
    assert.ok(!el.textContent.includes("could not be drawn"), screenName + " drew without an error");
    if (screenName === "coach") {
      assert.ok(all(el).some((n) => n.tag === "strong" && n.textContent === "Starter"), "bold lead");
      assert.ok(!all(el).some((n) => n.tag === "script"), "no markup from the model");
      assert.ok(el.textContent.includes("<script>x</script>"), "it is shown as text");
    }
  }
}
console.log("ok");
process.exit(0);
