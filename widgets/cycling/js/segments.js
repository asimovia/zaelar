// Cycling — segments: pick the ride to draw one on, the editor (mark a start and an end on the ride's route,
// snapped to it, the real path between them highlighted with its distance and climb), the segment's page (map,
// PR, its three best times, every attempt) and the ranking a new segment gets over every earlier ride.

import { tt, txt, btn, confirmBtn, dash, fmtSec, fmtKm, avgKmh, date, rideTitle, crumbs, stat } from "./util.js";
import { tileMap } from "./map.js";

const R = 6371000, rad = Math.PI / 180;
function hav(a, b) { const dl = (b[0] - a[0]) * rad, dn = (b[1] - a[1]) * rad;
  const h = Math.sin(dl / 2) ** 2 + Math.cos(a[0] * rad) * Math.cos(b[0] * rad) * Math.sin(dn / 2) ** 2; return 2 * R * Math.asin(Math.sqrt(h)); }
function nearestIdx(pts, ll) { let bi = 0, bd = Infinity;
  pts.forEach((p, i) => { const d = (p[0] - ll[0]) ** 2 + (p[1] - ll[1]) ** 2; if (d < bd) { bd = d; bi = i; } }); return bi; }

// «Create segment» / «Redo the path»: first, which ride to draw it on. Rides under 1 minute or 500 m are tests.
export function renderPicker(el, d, ctx, nav) {
  const redo = nav.local.redoSeg;
  el.appendChild(crumbs([{ label: tt("crumb_menu", null, "Cycling"), go: () => nav.go("menu") },
    { label: redo ? tt("redo_path", null, "Redo the path") : tt("create_seg", null, "Create segment") }]));
  el.appendChild(txt("div", "cy-note cy-left", tt("pick_help", null,
    "Choose an earlier ride to mark the segment's start and end on it. Rides under 1 minute or 500 m are left out (they are usually tests).")));
  const rides = (d.rides || []).filter((s) => (s.duration_sec || 0) >= 60 && (s.distance_km || 0) >= 0.5 && s.status === "done");
  if (!rides.length) { el.appendChild(txt("div", "hb-empty-state", tt("no_rides_for_seg", null, "No ride long enough yet."))); return; }
  const list = txt("div", "cy-list");
  for (const r of rides) {
    const row = btn("cy-rowbtn", null, () => nav.go("editor", { ride: r.id }));
    const top = txt("div", "cy-row-top");
    top.appendChild(txt("b", null, r.name || date(r.started_at, { weekday: "short", day: "numeric", month: "short", year: "numeric" })));
    if (r.locality) top.appendChild(txt("span", "cy-muted", "· " + r.locality));
    row.appendChild(top);
    row.appendChild(txt("div", "cy-muted", fmtKm(r.distance_km) + " km · " + fmtSec(r.duration_sec) + (r.avg_speed_kmh ? " · " + r.avg_speed_kmh + " km/h" : "")));
    list.appendChild(row);
  }
  el.appendChild(list);
}

export function renderEditor(el, det, ctx, nav) {
  const E = nav.local.editor || (nav.local.editor = { start: null, end: null, mode: null, name: nav.local.redoName || "", saving: false });
  const redo = nav.local.redoSeg;
  el.appendChild(crumbs([{ label: tt("crumb_menu", null, "Cycling"), go: () => nav.go("menu") },
    { label: rideTitle(det.ride), go: () => nav.go("ride", { ride: det.ride.id }) },
    { label: redo ? tt("redo_path", null, "Redo the path") : tt("create_seg", null, "Create segment") }]));
  const pts = (det.route || []).map((p) => [p[0], p[1], p[2]]);
  if (pts.length < 2) { el.appendChild(txt("div", "hb-empty-state", tt("no_gps_ride", null, "This ride has no GPS points."))); return; }
  const status = E.mode === "start" ? tt("tap_start", null, "📍 Tap the map to mark the start")
    : E.mode === "end" ? tt("tap_end", null, "🏁 Tap the map to mark the end")
      : E.start != null && E.end != null ? tt("both_marked", null, "✓ Start and end marked") : tt("press_mark", null, "Press a button to mark");
  el.appendChild(txt("div", "cy-note", status));
  const marks = txt("div", "cy-row2");
  marks.appendChild(btn("hb-btn " + (E.mode === "start" ? "hb-btn--primary" : "hb-btn--secondary"), tt("mark_start", null, "Mark start") + (E.start != null ? " ✓" : ""),
    () => { E.mode = E.mode === "start" ? null : "start"; nav.repaint(); }));
  marks.appendChild(btn("hb-btn " + (E.mode === "end" ? "hb-btn--primary" : "hb-btn--secondary"), tt("mark_end", null, "Mark end") + (E.end != null ? " ✓" : ""),
    () => { E.mode = E.mode === "end" ? null : "end"; nav.repaint(); }));
  el.appendChild(marks);

  let slice = null, distM = 0, gain = 0;
  if (E.start != null && E.end != null) {
    const a = Math.min(E.start, E.end), b = Math.max(E.start, E.end);
    slice = pts.slice(a, b + 1);
    for (let i = 1; i < slice.length; i++) {
      distM += hav(slice[i - 1], slice[i]);
      if (slice[i][2] != null && slice[i - 1][2] != null && slice[i][2] > slice[i - 1][2]) gain += slice[i][2] - slice[i - 1][2];
    }
  }
  const box = txt("div", "cy-mapbox cy-mapbox-tall" + (E.mode ? " is-marking" : ""));
  el.appendChild(box);
  const dots = [];
  if (E.start != null) dots.push({ at: pts[E.start], cls: "cy-start" });
  if (E.end != null) dots.push({ at: pts[E.end], cls: "cy-end" });
  tileMap(box, { lines: [{ pts, cls: "cy-route" }, ...(slice ? [{ pts: slice, cls: "cy-highlight" }] : [])], dots, fitTo: pts,
    onTap: (ll) => { if (!E.mode) return; E[E.mode] = nearestIdx(pts, ll); E.mode = null; nav.repaint(); } }, "edit:" + det.ride.id);
  if (slice) {
    const g = txt("div", "cy-grid");
    g.appendChild(stat((distM / 1000).toFixed(2) + " km", tt("dist", null, "DIST")));
    g.appendChild(stat(Math.round(gain) + " m", tt("climb", null, "CLIMB")));
    el.appendChild(g);
  }
  const f = txt("label", "hb-field");
  f.appendChild(txt("span", "hb-label", tt("seg_name", null, "Segment name")));
  const inp = document.createElement("input");
  inp.className = "hb-input"; inp.value = E.name; inp.maxLength = 60;
  inp.placeholder = tt("seg_name_ph", null, "Segment name (e.g. Climb to the village)");
  f.appendChild(inp);
  el.appendChild(f);
  const row = txt("div", "cy-row2");
  row.appendChild(btn("hb-btn hb-btn--secondary", tt("reset", null, "Reset"), () => { E.start = E.end = E.mode = null; nav.repaint(); }));
  const save = btn("hb-btn hb-btn--primary", E.saving ? tt("processing", null, "Processing…") : tt("save_seg", null, "✓ Save"), async () => {
    E.saving = true; nav.repaint();
    const p = { ride: String(det.ride.id), name: E.name.trim(), start: pts[E.start].slice(0, 2), end: pts[E.end].slice(0, 2) };
    const res = redo ? await ctx.action("redo_segment", { ...p, segment: String(redo) }) : await ctx.action("create_segment", p);
    E.saving = false;
    if (res && res.ok) { nav.local.editor = null; nav.local.redoSeg = null; nav.local.ranking = res; nav.go("ranking", { segment: res.segment }); }
    else { nav.local.error = (res && res.error) || "error"; nav.repaint(); }
  });
  const ready = () => E.start != null && E.end != null && !!E.name.trim() && !E.saving;
  save.disabled = !ready();
  inp.oninput = () => { E.name = inp.value; save.disabled = !ready(); };
  row.appendChild(save);
  el.appendChild(row);
  if (nav.local.error) { el.appendChild(txt("div", "cy-note cy-warn", String(nav.local.error))); nav.local.error = null; }
}

export function renderRanking(el, d, ctx, nav) {
  const res = nav.local.ranking || {};
  const seg = (d.segments || []).find((s) => s.id === res.segment) || {};
  el.appendChild(crumbs([{ label: tt("crumb_menu", null, "Cycling"), go: () => nav.go("menu") }, { label: seg.name || res.name || tt("segment", null, "Segment") }]));
  el.appendChild(txt("div", "cy-note cy-left", (seg.distance_m ? (seg.distance_m / 1000).toFixed(2) + " km · " : "") +
    tt("passes_found", { n: res.passes || 0 }, "{n} pass(es) found in your history")));
  const list = txt("div", "cy-list");
  (res.ranking || []).forEach((p, i) => {
    const row = txt("div", "hb-card cy-rank");
    row.appendChild(txt("b", "cy-rank-n", String(i + 1)));
    row.appendChild(txt("b", "cy-rank-t", fmtSec(p.time_sec)));
    const bits = [date(p.started_at, { weekday: "short", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })];
    if (p.avg_speed_kmh) bits.push(p.avg_speed_kmh + " km/h");
    if (p.max_speed_kmh) bits.push("⚡ " + p.max_speed_kmh);
    if (p.avg_hr) bits.push("♥ " + p.avg_hr + (p.max_hr ? "/" + p.max_hr : ""));
    if (p.weather_temp_c != null) bits.push(Math.round(p.weather_temp_c) + "°C");
    row.appendChild(txt("span", "cy-muted", bits.join(" · ")));
    list.appendChild(row);
  });
  if (!(res.ranking || []).length) list.appendChild(txt("div", "cy-note", tt("no_passes", null, "No earlier ride goes through it yet.")));
  el.appendChild(list);
  if (res.segment) el.appendChild(btn("hb-btn hb-btn--secondary", tt("open_seg", null, "Open the segment"), () => nav.go("segment", { segment: res.segment })));
}

export function renderSegment(el, det, ctx, nav) {
  const s = det.segment;
  el.appendChild(crumbs([{ label: tt("crumb_menu", null, "Cycling"), go: () => nav.go("menu") }, { label: s.name || tt("segment", null, "Segment") }]));
  const head = txt("div", "cy-title-row");
  if (nav.local.editingName) {
    const inp = document.createElement("input");
    inp.className = "hb-input cy-title-input"; inp.value = s.name || ""; inp.maxLength = 60;
    inp.placeholder = tt("seg_name", null, "Segment name");
    const save = async () => { nav.local.editingName = false; await ctx.action("rename_segment", { segment: String(s.id), name: inp.value.trim() }); nav.reload(); };
    inp.onkeydown = (e) => { if (e.key === "Enter") save(); if (e.key === "Escape") { nav.local.editingName = false; nav.repaint(); } };
    head.appendChild(inp);
    head.appendChild(btn("hb-iconbtn", "✓", save, tt("save_name", null, "Save")));
  } else {
    head.appendChild(txt("h3", "cy-title", s.name || tt("segment", null, "Segment")));
    head.appendChild(btn("hb-iconbtn", "✎", () => { nav.local.editingName = true; nav.repaint(); }, tt("rename", null, "Rename")));
  }
  head.appendChild(confirmBtn("hb-iconbtn hb-iconbtn--danger", "🗑", async () => { await ctx.action("delete_segment", { segment: String(s.id) }); nav.go("menu"); },
    tt("delete_seg", null, "Delete segment")));
  el.appendChild(head);

  if ((det.polyline || []).length >= 2) {
    const box = txt("div", "cy-mapbox");
    el.appendChild(box);
    tileMap(box, { lines: [{ pts: det.polyline, cls: "cy-seg" }], dots: [{ at: [s.start_lat, s.start_lng], cls: "cy-start" }, { at: [s.end_lat, s.end_lng], cls: "cy-end" }],
      fitTo: det.polyline }, "seg:" + s.id + ":" + det.polyline.length);
  }
  const g = txt("div", "cy-grid");
  g.appendChild(stat(s.distance_m ? (s.distance_m / 1000).toFixed(2) : dash, tt("km", null, "km")));
  g.appendChild(stat(s.pr_time_sec ? fmtSec(s.pr_time_sec) : dash, tt("pr", null, "PR"), "is-accent"));
  g.appendChild(stat(det.pr_speed_kmh != null ? String(det.pr_speed_kmh) : dash, tt("pr_avg", null, "PR avg km/h")));
  g.appendChild(stat(String(s.attempts || (det.attempts || []).length || 0), tt("attempts", null, "attempts")));
  el.appendChild(g);
  const row = txt("div", "cy-row2");
  row.appendChild(btn("hb-btn hb-btn--secondary", nav.local.recalcBusy ? tt("processing", null, "Processing…") : tt("recalc", null, "↻ Recalculate passes"), async () => {
    nav.local.recalcBusy = true; nav.repaint();
    await ctx.action("recalc_segment", { segment: String(s.id) });
    nav.local.recalcBusy = false; nav.reload();
  }));
  row.appendChild(btn("hb-btn hb-btn--secondary", tt("redo_path", null, "Redo the path"), () => {
    nav.local.redoSeg = s.id; nav.local.redoName = s.name || ""; nav.go("segments", { keepRedo: true });
  }));
  el.appendChild(row);

  const top = txt("div", "hb-panel cy-panel");
  top.appendChild(txt("div", "hb-panel-title", tt("best_times", null, "🏆 Best times")));
  (det.top3 || []).forEach((a, i) => {
    const r = txt("div", "cy-board");
    r.appendChild(txt("b", "cy-rank-n", String(i + 1)));
    r.appendChild(txt("b", "cy-rank-t", fmtSec(a.time_sec)));
    const bits = [date(a.started_at, { day: "numeric", month: "short", year: "numeric" }), avgKmh(s.distance_m, a.time_sec) + " km/h"];
    if (a.temp_c != null) bits.push(Math.round(a.temp_c) + "°C");
    r.appendChild(txt("span", "cy-muted", bits.join(" · ")));
    top.appendChild(r);
  });
  if (!(det.top3 || []).length) top.appendChild(txt("div", "cy-note", tt("no_attempts", null, "No attempts recorded yet.")));
  el.appendChild(top);

  const all = txt("div", "hb-panel cy-panel");
  all.appendChild(txt("div", "hb-panel-title", tt("attempts_title", null, "Attempts")));
  for (const a of det.attempts || []) {
    const r = btn("cy-rowbtn", null, () => nav.go("ride", { ride: a.session_id }));
    const t = txt("div", "cy-row-top");
    t.appendChild(txt("b", null, fmtSec(a.time_sec)));
    if (a.is_pr) t.appendChild(txt("span", "hb-badge hb-badge--ok", tt("pr_badge", null, "🏆 PR")));
    t.appendChild(txt("span", "cy-muted", date(a.started_at, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })));
    r.appendChild(t);
    const bits = ["💨 " + avgKmh(s.distance_m, a.time_sec) + " km/h"];
    if (a.max_speed_kmh) bits.push("⚡ " + Number(a.max_speed_kmh).toFixed(1));
    if (a.avg_hr) bits.push("♥ " + a.avg_hr);
    if (a.temp_c != null) bits.push("🌡 " + Math.round(a.temp_c) + "°C");
    r.appendChild(txt("div", "cy-muted", bits.join(" · ")));
    all.appendChild(r);
  }
  if (!(det.attempts || []).length) all.appendChild(txt("div", "cy-note", tt("no_attempts_hint", null, "No attempts yet: ride through it and save the ride.")));
  el.appendChild(all);
}
