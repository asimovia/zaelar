// Cycling — one ride's page: the route on the map, its figures, the analysis (moving time, climb), heart-rate and
// elevation profiles, the 1-km splits, the segments it crossed (with the PR delta), and the GPS gaps it has with the
// way to rebuild them along real roads. Its data comes from the `ride_detail` action (the card cannot fetch).

import { tt, txt, btn, confirmBtn, dash, fmtSec, fmtKm, date, rideTitle, crumbs, stat, sparkline } from "./util.js";
import { tileMap } from "./map.js";

export function renderDetail(el, det, ctx, nav) {
  const r = det.ride;
  el.appendChild(crumbs([{ label: tt("crumb_menu", null, "Cycling"), go: () => nav.go("menu") },
    { label: tt("rides", null, "Rides"), go: () => nav.go("history") }, { label: rideTitle(r) }]));

  // Title: rename in place.
  const head = txt("div", "cy-title-row");
  if (nav.local.editingName) {
    const inp = document.createElement("input");
    inp.className = "hb-input cy-title-input"; inp.value = r.name || ""; inp.maxLength = 60;
    inp.placeholder = tt("name_ph", null, "Name this ride");
    const save = async () => { nav.local.editingName = false; await ctx.action("rename_ride", { ride: String(r.id), name: inp.value.trim() }); nav.reload(); };
    inp.onkeydown = (e) => { if (e.key === "Enter") save(); if (e.key === "Escape") { nav.local.editingName = false; nav.repaint(); } };
    head.appendChild(inp);
    head.appendChild(btn("hb-iconbtn", "✓", save, tt("save_name", null, "Save")));
  } else {
    head.appendChild(txt("h3", "cy-title", rideTitle(r)));
    head.appendChild(btn("hb-iconbtn", "✎", () => { nav.local.editingName = true; nav.repaint(); }, tt("rename", null, "Rename")));
  }
  head.appendChild(confirmBtn("hb-iconbtn hb-iconbtn--danger", "🗑", async () => { await ctx.action("delete_ride", { ride: String(r.id) }); nav.go("history"); },
    tt("delete_ride", null, "Delete ride")));
  el.appendChild(head);
  const sub = [date(r.started_at, { weekday: "long", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })];
  if (r.locality) sub.push(r.locality);
  if (r.weather_temp_c != null) sub.push(Math.round(r.weather_temp_c) + "°C");
  el.appendChild(txt("div", "cy-note cy-left", sub.join(" · ")));

  if (det.route && det.route.length) {
    const box = txt("div", "cy-mapbox");
    el.appendChild(box);
    const pts = det.route.map((p) => [p[0], p[1]]);
    tileMap(box, { lines: [{ pts, cls: "cy-route" }], dots: [{ at: pts[0], cls: "cy-start" }, { at: pts[pts.length - 1], cls: "cy-end" }], fitTo: pts },
      "ride:" + r.id + ":" + pts.length);
  } else {
    el.appendChild(txt("div", "hb-empty-state", tt("no_gps", null, "No GPS data")));
  }

  const p1 = txt("div", "hb-panel cy-panel");
  const g = txt("div", "cy-grid");
  g.appendChild(stat(fmtSec(r.duration_sec || 0), tt("time", null, "TIME")));
  g.appendChild(stat(fmtKm(r.distance_km || 0), tt("dist_km", null, "DIST. (km)")));
  g.appendChild(stat(r.avg_speed_kmh != null ? Number(r.avg_speed_kmh).toFixed(2) : dash, tt("avg_kmh", null, "AVG (km/h)")));
  g.appendChild(stat(r.max_speed_kmh != null ? Number(r.max_speed_kmh).toFixed(2) : dash, tt("max_kmh", null, "MAX (km/h)")));
  g.appendChild(stat(r.avg_hr ? String(r.avg_hr) : dash, tt("hr_avg", null, "♥ AVG")));
  g.appendChild(stat(r.max_hr ? String(r.max_hr) : dash, tt("hr_max", null, "♥ MAX")));
  p1.appendChild(g);
  if (det.trackpoint_count) {
    p1.appendChild(txt("div", "cy-note cy-left", tt("tps", { n: det.trackpoint_count }, "Trackpoints: {n}") +
      (det.reconstructed_count ? " · " + tt("tps_rebuilt", { n: det.reconstructed_count }, "{n} rebuilt") : "")));
  }
  el.appendChild(p1);

  if (det.stats) {
    const p2 = txt("div", "hb-panel cy-panel");
    p2.appendChild(txt("div", "hb-panel-title", tt("analysis", null, "Analysis")));
    const g2 = txt("div", "cy-grid");
    g2.appendChild(stat(fmtSec(det.stats.moving_time_sec || 0), tt("moving", null, "MOVING TIME")));
    g2.appendChild(stat((det.stats.elevation_gain_m || 0) + " m", tt("elev_up", null, "CLIMB +")));
    g2.appendChild(stat((det.stats.elevation_loss_m || 0) + " m", tt("elev_down", null, "DESCENT −")));
    p2.appendChild(g2);
    if ((det.hr || []).length > 1) {
      p2.appendChild(txt("div", "hb-sectitle", tt("hr_profile", null, "Heart rate")));
      p2.appendChild(sparkline(det.hr, "cy-spark-hr"));
    }
    if ((det.elevation || []).length > 1) {
      p2.appendChild(txt("div", "hb-sectitle", tt("elev_profile", null, "Elevation")));
      p2.appendChild(sparkline(det.elevation, "cy-spark-elev"));
    }
    el.appendChild(p2);
  }

  if ((det.splits || []).length) {
    const p3 = txt("div", "hb-panel cy-panel");
    p3.appendChild(txt("div", "hb-panel-title", tt("splits", null, "Splits · every km")));
    const ul = txt("div", "cy-list");
    for (const s of det.splits) {
      const li = txt("div", "cy-split");
      li.appendChild(txt("b", null, tt("split_km", { n: s.idx }, "{n} km")));
      li.appendChild(txt("span", null, fmtSec(s.duration_sec)));
      li.appendChild(txt("span", null, s.avg_speed_kmh + " km/h"));
      li.appendChild(txt("span", "cy-muted", s.elevation_gain_m ? "+" + s.elevation_gain_m + "m" : ""));
      li.appendChild(txt("span", "cy-muted", s.avg_hr ? "♥ " + s.avg_hr : ""));
      ul.appendChild(li);
    }
    p3.appendChild(ul);
    el.appendChild(p3);
  }

  const p4 = txt("div", "hb-panel cy-panel");
  p4.appendChild(txt("div", "hb-panel-title", tt("segs_in_ride", null, "Segments on this ride")));
  if ((det.attempts || []).length) {
    for (const a of det.attempts) {
      const row = btn("cy-rowbtn", null, () => nav.go("segment", { segment: a.segment_id }));
      const top = txt("div", "cy-row-top");
      top.appendChild(txt("b", null, a.segment_name || tt("segment", null, "Segment")));
      if (a.is_pr) top.appendChild(txt("span", "hb-badge hb-badge--ok", tt("pr_badge", null, "🏆 PR")));
      row.appendChild(top);
      const bits = [fmtSec(a.time_sec)];
      if (a.distance_m) bits.push((a.distance_m / 1000).toFixed(2) + " km");
      if (a.avg_speed_kmh) bits.push(a.avg_speed_kmh + " km/h");
      if (a.avg_hr) bits.push("♥ " + a.avg_hr);
      if (a.pr_time_sec && a.time_sec !== a.pr_time_sec) bits.push("Δ " + (a.time_sec > a.pr_time_sec ? "+" : "−") + fmtSec(Math.abs(a.time_sec - a.pr_time_sec)));
      row.appendChild(txt("div", "cy-muted", bits.join(" · ")));
      p4.appendChild(row);
    }
  } else {
    p4.appendChild(txt("div", "cy-note cy-left", tt("no_segs_in_ride", null, "You did not ride through any known segment on this ride.")));
  }
  el.appendChild(p4);

  if (det.trackpoint_count) {
    const p5 = txt("div", "hb-panel cy-panel");
    p5.appendChild(txt("div", "hb-panel-title", tt("gaps", null, "GPS gaps")));
    p5.appendChild(txt("div", "cy-note cy-left", tt("gaps_help", null,
      "If the phone slept or the app was closed, the GPS has holes. This rebuilds the lost stretches along real roads.")));
    const gaps = det.gaps || [];
    p5.appendChild(txt("div", "cy-note cy-left", tt("gaps_found", { n: gaps.length }, "{n} gap(s) over 30 s")));
    for (const gp of gaps.slice(0, 5)) p5.appendChild(txt("div", "cy-muted", "· " + tt("gap_line", { t: fmtSec(gp.gap_sec) }, "{t} without readings")));
    if (nav.local.recon) {
      const rr = nav.local.recon;
      p5.appendChild(txt("div", "cy-note cy-left", tt("recon_done", { f: rr.gaps_filled, n: rr.gaps_found, p: rr.trackpoints_inserted,
        km: ((rr.distance_added_m || 0) / 1000).toFixed(2) }, "Rebuilt {f}/{n} · {p} virtual points · +{km} km")));
    }
    const b = btn("hb-btn hb-btn--primary", nav.local.reconBusy ? tt("rebuilding", null, "Rebuilding…") : tt("rebuild", null, "Rebuild and save"), async () => {
      nav.local.reconBusy = true; nav.repaint();
      const res = await ctx.action("reconstruct_gaps", { ride: String(r.id) });
      nav.local.reconBusy = false; nav.local.recon = res && res.ok ? res : null;
      nav.reload();
    });
    b.disabled = !gaps.length || !!nav.local.reconBusy;
    p5.appendChild(b);
    el.appendChild(p5);
  }

  el.appendChild(btn("hb-btn hb-btn--secondary", tt("make_segment", null, "Create a segment from this ride"), () => nav.go("editor", { ride: r.id })));
}
