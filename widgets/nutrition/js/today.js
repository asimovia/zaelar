// Nutrition — the TODAY screen: the day's balance, the capture (photo and/or words, or numbers) and the meals.

import { S, go, repaint } from "./state.js";
import { btn, errorText, field, fmtDay, fmtNum, fmtTime, h, hue, input, localNow, logicalToday, numIn, parseDecimal,
  qualityRating, shiftDay, tt } from "./ui.js";

const MACROS = () => [
  ["calories", tt("kcal", null, "kcal")], ["protein_g", tt("protein_g", null, "Protein g")],
  ["carbs_g", tt("carbs_g", null, "Carbs g")], ["fat_g", tt("fat_g", null, "Fat g")], ["fiber_g", tt("fiber_g", null, "Fibre g")],
];
const COMPONENT = (k) => ({
  veg: tt("comp_veg", null, "Vegetables"), leg: tt("comp_leg", null, "Legumes"), prot: tt("comp_prot", null, "Lean protein"),
  fruit: tt("comp_fruit", null, "Fruit"), grain: tt("comp_grain", null, "Wholegrain"), fat: tt("comp_fat", null, "Good fat"),
  water: tt("comp_water", null, "Hydration"),
})[k] || k;
const QUALITY = (avg) => avg == null ? tt("quality_none", null, "No data yet") : avg >= 4 ? tt("quality_high", null, "High quality")
  : avg >= 3 ? tt("quality_medium", null, "Medium quality") : avg >= 2 ? tt("quality_low", null, "Low quality") : tt("quality_very_low", null, "Very low");

export function dayShown(d) { return S.day || (d.days && d.days.length ? d.days[d.days.length - 1].date : logicalToday()); }

function dayHead(d) {
  const day = dayShown(d), today = (d.days && d.days.length) ? d.days[d.days.length - 1].date : logicalToday();
  const row = h("div", "nu-dayhead");
  const prev = btn("hb-btn--ghost hb-btn--sm", "‹", () => { go("today", shiftDay(day, -1)); repaint(); }, tt("prev_day", null, "Previous day"));
  const next = btn("hb-btn--ghost hb-btn--sm", "›", () => { const n = shiftDay(day, 1); go("today", n >= today ? null : n); repaint(); }, tt("next_day", null, "Next day"));
  next.disabled = day >= today;
  row.appendChild(prev);
  row.appendChild(h("b", null, day === today ? tt("today_is", { day: fmtDay(day, true) }, "Today · {day}") : fmtDay(day, true)));
  row.appendChild(next);
  return row;
}

function balance(d, meals, dayRow) {
  const p = h("div", "nu-panel");
  const t = d.targets || {};
  const kin = dayRow ? dayRow.kcal_in : 0;
  const big = h("div", "nu-big");
  big.appendChild(h("b", null, fmtNum(kin)));
  big.appendChild(h("span", null, tt("of_target", { n: fmtNum(t.calories) }, "of {n} kcal")));
  p.appendChild(big);
  const track = h("div", "nu-track"), fill = h("div", "nu-fill");
  fill.style.width = Math.min(100, t.calories ? Math.round(kin / t.calories * 100) : 0) + "%";
  fill.style.background = hue(qualityRating(dayRow ? dayRow.health_avg : null));
  track.appendChild(fill);
  p.appendChild(track);
  const delta = Math.round(kin - (t.calories || 0));
  const status = dayRow && dayRow.goal_status;
  p.appendChild(h("div", "nu-note", !status ? tt("nothing_logged", null, "Nothing logged this day yet.")
    : status === "on" ? tt("goal_on", null, "On target.")
      : status === "over" ? tt("goal_over", { n: fmtNum(delta) }, "{n} kcal over the target.")
        : tt("goal_low", { n: fmtNum(-delta) }, "{n} kcal left to the target.")));
  const macros = h("div", "nu-macros");
  const mac = (v, label, target) => {
    const m = h("div", "nu-macro");
    m.appendChild(h("b", null, fmtNum(v) + (target ? " / " + fmtNum(target) : "")));
    m.appendChild(h("span", null, label));
    return m;
  };
  macros.appendChild(mac(dayRow ? dayRow.protein_g : 0, tt("protein_g", null, "Protein g"), t.protein_g));
  macros.appendChild(mac(dayRow ? dayRow.carbs_g : 0, tt("carbs_g", null, "Carbs g")));
  macros.appendChild(mac(dayRow ? dayRow.fat_g : 0, tt("fat_g", null, "Fat g")));
  macros.appendChild(mac(dayRow ? dayRow.fiber_g : 0, tt("fiber_g", null, "Fibre g")));
  p.appendChild(macros);
  if (dayRow && dayRow.score != null) {
    const row = h("div", "nu-row");
    const sc = h("span", "nu-score");
    sc.appendChild(h("b", null, String(dayRow.score)));
    sc.appendChild(h("span", "nu-note", "/100"));
    row.appendChild(h("span", "nu-note", tt("day_score", null, "Day score")));
    row.appendChild(sc);
    const cls = dayRow.score >= 75 ? "ok" : dayRow.score >= 55 ? "warn" : "error";
    row.appendChild(h("span", "hb-badge hb-badge--" + cls, QUALITY(dayRow.health_avg)));
    p.appendChild(row);
    const comps = h("div", "nu-comps");
    for (const k of d.components_all || []) {
      const on = (dayRow.components || []).includes(k);
      const c = h("span", "nu-comp" + (on ? " is-on" : ""), (on ? "✓ " : "") + COMPONENT(k));
      comps.appendChild(c);
    }
    p.appendChild(comps);
  }
  return p;
}

async function saveCapture(ctx, d) {
  const text = S.draft.trim();
  const nums = {};
  if (S.manual) for (const [k] of MACROS()) { const v = parseDecimal(S.manualVals[k]); if (v != null) nums[k] = v; }
  if (!text && !S.photo && nums.calories == null) return;
  S.busy = true; S.error = ""; repaint();
  let photo = null;
  if (S.photo) {
    const up = typeof ctx.upload === "function" ? await ctx.upload(await shrink(S.photo.file)) : { error: "upload_failed" };
    if (!up || up.error || !up.name) { S.busy = false; S.error = errorText("upload_failed"); repaint(); return; }
    photo = up.name;
  }
  const day = dayShown(d), today = logicalToday();
  const eaten_at = day === today ? localNow() : day + "T13:00";
  const payload = { text, eaten_at, lang: ctx.lang || "en", ...nums };
  if (photo) payload.photo = photo;
  if (S.manual && nums.calories != null && !text) payload.description = S.manualVals.description || "";
  const r = await ctx.action("log_meal", payload);
  S.busy = false;
  if (!r || r.ok === false) { S.error = errorText(r && r.error); repaint(); return; }
  if (S.photo) { try { URL.revokeObjectURL(S.photo.url); } catch (_) {} }
  S.draft = ""; S.photo = null; S.manual = false; S.manualVals = {};
  if (r.status === "failed") { S.meal = r.meal_id; S.mode = "edit"; S.error = errorText(r.reason); }
  repaint();
}

// A phone photo is several MB; the estimate needs ~1600 px. Shrunk on the screen, the original never leaves it.
export async function shrink(file) {
  try {
    if (!file || file.size < 1_500_000 || typeof createImageBitmap !== "function") return file;
    const bmp = await createImageBitmap(file);
    const k = Math.min(1, 1600 / Math.max(bmp.width, bmp.height));
    const c = document.createElement("canvas");
    c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
    c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
    const blob = await new Promise((res) => c.toBlob(res, "image/jpeg", 0.85));
    return blob ? new File([blob], (file.name || "meal").replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg" }) : file;
  } catch (_) { return file; }
}

export function photoPicker(label, multiple, onPick) {
  const wrap = h("label", "hb-btn hb-btn--secondary nu-file", label);
  const f = document.createElement("input");
  f.type = "file"; f.accept = "image/*";
  f.setAttribute("capture", "environment");
  if (multiple) f.multiple = true;
  f.onchange = () => { const files = Array.from(f.files || []); f.value = ""; if (files.length) onPick(files); };
  wrap.appendChild(f);
  return wrap;
}

function capture(ctx, d) {
  const p = h("div", "nu-panel");
  p.appendChild(h("h4", null, tt("log_meal", null, "Log a meal")));
  const ta = document.createElement("textarea");
  ta.className = "hb-textarea";
  ta.placeholder = tt("capture_ph", null, "What did you eat? Portions, how it was cooked, the brand… or just say it to me.");
  ta.value = S.draft;
  ta.oninput = () => { S.draft = ta.value; };
  p.appendChild(ta);
  const row = h("div", "nu-row");
  row.appendChild(photoPicker(S.photo ? tt("change_photo", null, "Change photo") : tt("add_photo", null, "📷 Photo"), false, (files) => {
    if (S.photo) { try { URL.revokeObjectURL(S.photo.url); } catch (_) {} }
    S.photo = { file: files[0], url: URL.createObjectURL(files[0]) };
    repaint();
  }));
  if (S.photo) {
    const im = h("img", "nu-thumb"); im.src = S.photo.url; im.alt = tt("photo_ready", null, "Photo ready");
    row.appendChild(im);
    row.appendChild(btn("hb-btn--ghost hb-btn--sm", "✕", () => { try { URL.revokeObjectURL(S.photo.url); } catch (_) {} S.photo = null; repaint(); },
      tt("remove_photo", null, "Remove photo")));
  }
  row.appendChild(btn("hb-btn--ghost hb-btn--sm", S.manual ? tt("hide_numbers", null, "Hide numbers") : tt("enter_numbers", null, "Enter numbers"),
    () => { S.manual = !S.manual; repaint(); }));
  row.appendChild(h("span", "nu-grow"));
  const save = btn("hb-btn--primary", S.busy ? tt("saving", null, "Saving…") : tt("save", null, "Save"), () => saveCapture(ctx, d));
  save.disabled = S.busy;
  row.appendChild(save);
  p.appendChild(row);
  if (S.manual) {
    const form = h("div", "nu-form");
    const desc = input("text", S.manualVals.description || "", "", {});
    desc.oninput = () => { S.manualVals.description = desc.value; };
    form.appendChild(field(tt("description", null, "Description"), desc));
    for (const [k, label] of MACROS()) {
      const i = numIn(S.manualVals[k]);
      i.oninput = () => { S.manualVals[k] = i.value; };
      form.appendChild(field(label, i));
    }
    p.appendChild(form);
  }
  if (!(d.estimator && d.estimator.available)) {
    p.appendChild(h("div", "nu-note", tt("no_estimator", null, "Automatic estimates from a photo or words are not available yet: the meal is saved and you can enter its calories.")));
  }
  if (S.error) p.appendChild(h("div", "nu-warn", S.error));
  return p;
}

function mealDetail(ctx, m) {
  const box = h("div", "nu-detail");
  if (m.photo_url) { const im = h("img", "nu-photo"); im.src = m.photo_url; im.alt = m.description || ""; box.appendChild(im); }
  if (m.source_text) box.appendChild(h("div", "nu-note", "«" + m.source_text + "»"));
  if (m.status === "done") {
    const macros = h("div", "nu-macros");
    for (const [k, label] of MACROS()) {
      const c = h("div", "nu-macro"); c.appendChild(h("b", null, fmtNum(m[k], k === "calories" ? 0 : 1))); c.appendChild(h("span", null, label));
      macros.appendChild(c);
    }
    box.appendChild(macros);
  }
  if (m.health_score) {
    box.appendChild(h("div", "nu-row", tt("quality_meal", { n: m.health_score }, "Quality {n}/5") + (m.health_reason ? " · " + m.health_reason : "")));
  }
  if ((m.ingredients || []).length) {
    const wrap = h("div", "nu-wrap"), tab = h("table", "nu-ings");
    for (const i of m.ingredients) {
      const tr = h("tr");
      tr.appendChild(h("td", null, i.item || ""));
      tr.appendChild(h("td", null, fmtNum(i.grams) + " g"));
      tr.appendChild(h("td", null, fmtNum(i.kcal) + " kcal"));
      tr.appendChild(h("td", null, "P " + fmtNum(i.p) + " · C " + fmtNum(i.c) + " · F " + fmtNum(i.f)));
      tab.appendChild(tr);
    }
    wrap.appendChild(tab);
    box.appendChild(wrap);
  }
  if (m.notes) box.appendChild(h("div", "nu-note", m.notes));
  if (m.status === "failed") box.appendChild(h("div", "nu-warn", errorText(m.error)));
  const acts = h("div", "nu-row");
  if (m.status === "failed" && (m.source_text || m.photo_url)) {
    acts.appendChild(btn("hb-btn--secondary hb-btn--sm", tt("retry", null, "Retry"), async () => { await ctx.action("retry_meal", { meal_id: m.id, lang: ctx.lang || "en" }); }));
  }
  acts.appendChild(btn("hb-btn--secondary hb-btn--sm", tt("refine", null, "Add detail"), () => { S.mode = S.mode === "refine" ? null : "refine"; repaint(); }));
  acts.appendChild(btn("hb-btn--secondary hb-btn--sm", tt("edit", null, "Edit"), () => { S.mode = S.mode === "edit" ? null : "edit"; repaint(); }));
  acts.appendChild(h("span", "nu-grow"));
  acts.appendChild(btn("hb-btn--danger hb-btn--sm", tt("delete", null, "Delete"), async () => { await ctx.action("delete_meal", { meal_id: m.id }); go("today", S.day); }));
  box.appendChild(acts);
  if (S.mode === "refine") box.appendChild(refineForm(ctx, m));
  if (S.mode === "edit") box.appendChild(editForm(ctx, m));
  return box;
}

function toLocalInput(s) { return String(s || "").slice(0, 16); }

function refineForm(ctx, m) {
  const f = h("div", "nu-panel");
  const ta = document.createElement("textarea");
  ta.className = "hb-textarea";
  ta.placeholder = tt("refine_ph", null, "I only ate half · it was fried · it was the light version…");
  f.appendChild(ta);
  const when = input("datetime-local", toLocalInput(m.eaten_at));
  f.appendChild(field(tt("time", null, "Time"), when));
  const row = h("div", "nu-row");
  row.appendChild(btn("hb-btn--secondary hb-btn--sm", tt("cancel", null, "Cancel"), () => { S.mode = null; repaint(); }));
  row.appendChild(btn("hb-btn--primary hb-btn--sm", tt("save", null, "Save"), async () => {
    const payload = { meal_id: m.id, lang: ctx.lang || "en" };
    if (ta.value.trim()) payload.text = ta.value.trim();
    if (when.value && when.value !== toLocalInput(m.eaten_at)) payload.eaten_at = when.value;
    if (!payload.text && !payload.eaten_at) { S.mode = null; repaint(); return; }
    S.mode = null;
    await ctx.action("refine_meal", payload);
  }));
  f.appendChild(row);
  return f;
}

function editForm(ctx, m) {
  const f = h("div", "nu-panel"), form = h("div", "nu-form"), ins = {};
  ins.description = input("text", m.description || m.source_text || "");
  form.appendChild(field(tt("description", null, "Description"), ins.description));
  for (const [k, label] of MACROS()) { ins[k] = numIn(m[k]); form.appendChild(field(label, ins[k])); }
  ins.health_score = numIn(m.health_score, "1", { inputmode: "numeric" });
  form.appendChild(field(tt("quality_1_5", null, "Quality 1-5"), ins.health_score));
  ins.eaten_at = input("datetime-local", toLocalInput(m.eaten_at));
  form.appendChild(field(tt("time", null, "Time"), ins.eaten_at));
  f.appendChild(form);
  const row = h("div", "nu-row");
  row.appendChild(btn("hb-btn--secondary hb-btn--sm", tt("cancel", null, "Cancel"), () => { S.mode = null; repaint(); }));
  row.appendChild(btn("hb-btn--primary hb-btn--sm", tt("save", null, "Save"), async () => {
    const p = { meal_id: m.id, description: ins.description.value.trim() };
    for (const [k] of MACROS()) { const v = parseDecimal(ins[k].value); if (v != null || m[k] != null) p[k] = v; }
    const hs = parseDecimal(ins.health_score.value); if (hs != null) p.health_score = hs;
    if (ins.eaten_at.value && ins.eaten_at.value !== toLocalInput(m.eaten_at)) p.eaten_at = ins.eaten_at.value;
    S.mode = null; S.error = "";
    await ctx.action("edit_meal", p);
  }));
  f.appendChild(row);
  return f;
}

function mealRow(ctx, m) {
  const open = S.meal === m.id;
  const card = h("div", "nu-meal");
  card.style.setProperty("--nu-hue", hue(m.rating || "gray"));
  const head = h("button", "nu-meal-head");
  head.type = "button";
  head.setAttribute("aria-expanded", open ? "true" : "false");
  head.onclick = () => { if (open) go("today", S.day); else { go("today", S.day, m.id); } repaint(); };
  if (m.photo_url) { const im = h("img", "nu-thumb"); im.src = m.photo_url; im.alt = ""; head.appendChild(im); }
  head.appendChild(h("span", "nu-time", fmtTime(m.eaten_at)));
  head.appendChild(h("span", "nu-grow", m.description || m.source_text || tt("meal", null, "Meal")));
  if (m.status === "pending") head.appendChild(h("span", "hb-badge hb-badge--info", tt("pending", null, "Estimating…")));
  else if (m.status === "failed") head.appendChild(h("span", "hb-badge hb-badge--warn", tt("needs_numbers", null, "No estimate")));
  else head.appendChild(h("span", "nu-kcal", fmtNum(m.calories) + " kcal"));
  card.appendChild(head);
  if (open) card.appendChild(mealDetail(ctx, m));
  return card;
}

export function todayScreen(root, d, ctx) {
  const day = dayShown(d);
  const dayRow = (d.days || []).find((x) => x.date === day) || null;
  const meals = (d.meals || []).filter((m) => m.day === day);
  root.appendChild(dayHead(d));
  root.appendChild(balance(d, meals, dayRow));
  root.appendChild(capture(ctx, d));
  const list = h("div", "nu-meals");
  list.appendChild(h("h4", null, tt("meals_of_day", { n: meals.length }, "Meals · {n}")));
  if (!meals.length) list.appendChild(h("div", "hb-empty-state nu-note", tt("no_meals", null, "No meals logged. Take a photo, write it, or tell me what you ate.")));
  for (const m of meals) list.appendChild(mealRow(ctx, m));
  if (d.bin_n) list.appendChild(btn("hb-btn--ghost hb-btn--sm", tt("restore", null, "↶ Restore the last removed"), () => ctx.action("restore", {})));
  root.appendChild(list);
  return { day, meal: S.meal && meals.some((m) => m.id === S.meal) ? S.meal : "", pending: meals.filter((m) => m.status === "pending").length };
}
