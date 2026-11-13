// Nutrition — the WEIGHT screen: log a measurement, the 30-day chart, the 30-day quality strip and the history.

import { S, repaint } from "./state.js";
import { btn, field, fmtDay, fmtNum, h, hue, input, localNow, numIn, parseDecimal, tt } from "./ui.js";

const SVG = "http://www.w3.org/2000/svg";
const BODY = () => [
  ["weight_kg", tt("weight_kg", null, "Weight kg")], ["body_fat_pct", tt("body_fat_pct", null, "Body fat %")],
  ["muscle_mass_kg", tt("muscle_mass_kg", null, "Muscle kg")], ["waist_cm", tt("waist_cm", null, "Waist cm")],
];

function svg(tag, attrs) {
  const e = document.createElementNS(SVG, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  return e;
}

// The source's chart: the readings of the last 30 days on a line with its area, min and max labelled.
export function weightChart(days) {
  const W = 320, H = 140, PAD = 20;
  const pts = (days || []).map((d, i) => ({ i, w: d.weight_kg })).filter((p) => p.w != null);
  const s = svg("svg", { class: "nu-chart", viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none", role: "img" });
  if (!pts.length) return null;
  const min = Math.min(...pts.map((p) => p.w)) - 0.5, max = Math.max(...pts.map((p) => p.w)) + 0.5;
  const N = (days || []).length || 30;
  const x = (i) => PAD + (i / Math.max(1, N - 1)) * (W - 2 * PAD);
  const y = (w) => H - PAD - ((w - min) / Math.max(0.1, max - min)) * (H - 2 * PAD);
  const line = pts.map((p, k) => `${k ? "L" : "M"}${x(p.i).toFixed(1)},${y(p.w).toFixed(1)}`).join(" ");
  const base = (H - PAD).toFixed(1);
  s.appendChild(svg("path", { class: "nu-area", d: `M${x(pts[0].i).toFixed(1)},${base} ` + pts.map((p) => `L${x(p.i).toFixed(1)},${y(p.w).toFixed(1)}`).join(" ") + ` L${x(pts[pts.length - 1].i).toFixed(1)},${base} Z` }));
  s.appendChild(svg("path", { class: "nu-line", d: line }));
  for (const p of pts) s.appendChild(svg("circle", { class: "nu-dot", cx: x(p.i).toFixed(1), cy: y(p.w).toFixed(1), r: 3 }));
  const lo = svg("text", { x: PAD, y: H - 4 }); lo.textContent = min.toFixed(1);
  const hi = svg("text", { x: PAD, y: PAD - 6 }); hi.textContent = max.toFixed(1);
  s.appendChild(lo); s.appendChild(hi);
  s.setAttribute("aria-label", tt("chart_label", { a: min.toFixed(1), b: max.toFixed(1) }, "Weight over 30 days, between {a} and {b} kg"));
  return s;
}

function strip(days) {
  const box = h("div", "nu-panel");
  box.appendChild(h("h4", null, tt("quality_30d", null, "Nutrition quality · 30 days")));
  const row = h("div", "nu-strip");
  for (const d of days || []) {
    const i = h("i");
    i.style.background = hue(d.rating);
    i.title = fmtDay(d.date) + " · " + (d.health_avg != null ? tt("avg_n", { n: d.health_avg }, "avg {n}/5") : tt("no_data", null, "no data"));
    row.appendChild(i);
  }
  box.appendChild(row);
  const leg = h("div", "nu-legend");
  for (const [r, label] of [["green", tt("leg_good", null, "good day")], ["yellow", tt("leg_ok", null, "acceptable")],
    ["red", tt("leg_bad", null, "off")], ["gray", tt("leg_none", null, "no data / lunch or dinner missing")]]) {
    const s = h("span"); const dot = h("i"); dot.style.background = hue(r); s.appendChild(dot); s.appendChild(document.createTextNode(label));
    leg.appendChild(s);
  }
  box.appendChild(leg);
  return box;
}

function logForm(ctx) {
  const p = h("div", "nu-panel");
  p.appendChild(h("h4", null, tt("log_weight", null, "Log a weigh-in")));
  const form = h("div", "nu-form"), ins = {};
  for (const [k, label] of BODY()) {
    if (k !== "weight_kg" && !S.moreBody) continue;
    ins[k] = numIn("");
    form.appendChild(field(label, ins[k]));
  }
  p.appendChild(form);
  const row = h("div", "nu-row");
  row.appendChild(btn("hb-btn--ghost hb-btn--sm", S.moreBody ? tt("fewer_fields", null, "Only weight") : tt("more_fields", null, "Fat, muscle, waist"),
    () => { S.moreBody = !S.moreBody; repaint(); }));
  row.appendChild(h("span", "nu-grow"));
  row.appendChild(btn("hb-btn--primary", tt("log", null, "Log"), async () => {
    const payload = { measured_at: localNow() };
    for (const k in ins) { const v = parseDecimal(ins[k].value); if (v != null) payload[k] = v; }
    if (Object.keys(payload).length < 2) { S.error = tt("invalid_weight", null, "Write a valid weight."); repaint(); return; }
    const r = await ctx.action("log_weight", payload);
    if (!r || r.ok === false) { S.error = tt("invalid_weight", null, "Write a valid weight."); repaint(); }
    else S.error = "";
  }));
  p.appendChild(row);
  if (S.error) p.appendChild(h("div", "nu-warn", S.error));
  return p;
}

function entryRow(ctx, b) {
  const li = h("div", "nu-li");
  if (S.weightOpen === b.id) {
    const form = h("div", "nu-form nu-grow"), ins = {};
    for (const [k, label] of BODY()) { ins[k] = numIn(b[k]); form.appendChild(field(label, ins[k])); }
    ins.measured_at = input("datetime-local", String(b.measured_at || "").slice(0, 16));
    form.appendChild(field(tt("date", null, "Date"), ins.measured_at));
    li.appendChild(form);
    li.appendChild(btn("hb-btn--secondary hb-btn--sm", tt("cancel", null, "Cancel"), () => { S.weightOpen = null; repaint(); }));
    li.appendChild(btn("hb-btn--primary hb-btn--sm", tt("save", null, "Save"), async () => {
      const p = { entry_id: b.id };
      for (const [k] of BODY()) { const v = parseDecimal(ins[k].value); if (v != null || b[k] != null) p[k] = v; }
      if (ins.measured_at.value) p.measured_at = ins.measured_at.value;
      S.weightOpen = null;
      await ctx.action("edit_weight", p);
    }));
    return li;
  }
  li.appendChild(h("b", null, b.weight_kg != null ? fmtNum(b.weight_kg, 1) + " kg" : "—"));
  const extra = [];
  if (b.body_fat_pct != null) extra.push(fmtNum(b.body_fat_pct, 1) + " %");
  if (b.muscle_mass_kg != null) extra.push(tt("muscle_short", { n: fmtNum(b.muscle_mass_kg, 1) }, "muscle {n} kg"));
  if (b.waist_cm != null) extra.push(tt("waist_short", { n: fmtNum(b.waist_cm) }, "waist {n} cm"));
  li.appendChild(h("span", "nu-note nu-grow", [fmtDay(b.measured_at), ...extra].join(" · ")));
  li.appendChild(btn("hb-btn--ghost hb-btn--sm", tt("edit", null, "Edit"), () => { S.weightOpen = b.id; repaint(); }));
  li.appendChild(btn("hb-btn--ghost hb-btn--sm", tt("delete", null, "Delete"), () => ctx.action("delete_weight", { entry_id: b.id })));
  return li;
}

export function weightScreen(root, d, ctx) {
  root.appendChild(logForm(ctx));
  const p = h("div", "nu-panel");
  const last = d.weight && d.weight.last;
  const big = h("div", "nu-big");
  big.appendChild(h("b", null, last ? fmtNum(last.weight_kg, 1) + " kg" : "—"));
  big.appendChild(h("span", null, last ? tt("last_on", { day: fmtDay(last.date) }, "last · {day}") : tt("no_weight", null, "No weigh-ins yet")));
  if (d.weight && d.weight.delta != null) {
    const dl = d.weight.delta;
    big.appendChild(h("span", "hb-badge hb-badge--bare", (dl > 0 ? "+" : "") + fmtNum(dl, 1) + " kg · 30d"));
  }
  p.appendChild(big);
  p.appendChild(h("h4", null, tt("weight_30d", null, "Weight · 30 days")));
  const chart = weightChart(d.days);
  p.appendChild(chart || h("div", "nu-note", tt("no_readings", null, "No readings yet")));
  root.appendChild(p);
  root.appendChild(strip(d.days));
  const hist = h("div", "nu-panel");
  hist.appendChild(h("h4", null, tt("history", null, "History")));
  const list = h("div", "nu-list");
  for (const b of d.body || []) list.appendChild(entryRow(ctx, b));
  if (!(d.body || []).length) list.appendChild(h("div", "nu-note", tt("no_weight", null, "No weigh-ins yet")));
  hist.appendChild(list);
  if (d.bin_n) hist.appendChild(btn("hb-btn--ghost hb-btn--sm", tt("restore", null, "↶ Restore the last removed"), () => ctx.action("restore", {})));
  root.appendChild(hist);
}
