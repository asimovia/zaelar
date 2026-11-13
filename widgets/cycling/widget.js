// Cycling — bike rides with the phone's GPS and a heart-rate strap, the ghost rider, segments and their PRs (V2-901).
// Ported from the person's previous app to work the same here. This file is the shell: one navigation transition,
// the menu (heart-rate zone, «ready to ride?», start, rides, segments, strap) and the history; the ride being
// recorded, a ride's page and the segment screens are in ./js. No network and no map library: data.py answers
// everything through ctx.action, and the maps are OpenStreetMap tiles drawn as plain images.

import { setT, tt, txt, btn, confirmBtn, dash, fmtSec, fmtKm, date, crumbs, light } from "./js/util.js";
import { injectStyles } from "./js/styles.js";
import { S, renderRide, stopSensors, recorderOf } from "./js/ride.js";
import { renderDetail } from "./js/detail.js";
import { renderPicker, renderEditor, renderRanking, renderSegment } from "./js/segments.js";

// The card's navigation (module state: it outlives the re-renders every data push causes). A screen change is ONE
// transition, `go`, whoever asks for it: a tap here, or a view the brain pushed through `show` (ui.n moved).
const N = { view: "menu", ride: null, segment: null, local: {}, cache: {}, seenN: null, readyAsked: false,
  enriching: false, enrichCount: 0, last: null };

function needs(view) { return view === "ride" || view === "editor" ? "ride" : view === "segment" ? "segment" : null; }

function makeNav(el, data, ctx) {
  const nav = {
    local: N.local,
    repaint: () => { if (el.isConnected && N.last) render(el, N.last.data, N.last.ctx); },
    go: (view, p = {}) => {
      const keep = view === "ranking" ? { ranking: N.local.ranking }
        : view === "segments" && p.keepRedo ? { redoSeg: N.local.redoSeg, redoName: N.local.redoName }
          : view === "editor" ? { redoSeg: N.local.redoSeg, redoName: N.local.redoName } : {};
      N.view = view; N.ride = p.ride != null ? p.ride : null; N.segment = p.segment != null ? p.segment : null;
      N.local = keep; nav.local = N.local;
      try { if (ctx.top) ctx.top(); } catch (_) {}
      nav.repaint();
    },
    reload: () => { const k = cacheKey(); if (k) delete N.cache[k]; nav.repaint(); },
  };
  return nav;
}

function cacheKey() {
  const kind = needs(N.view);
  return kind === "ride" ? "ride:" + N.ride : kind === "segment" ? "segment:" + N.segment : null;
}

// The summary row of what a page shows: when it changes (renamed by voice, a new attempt), the page reloads.
function stamp(data) {
  const kind = needs(N.view);
  if (kind === "ride") return JSON.stringify((data.rides || []).find((r) => r.id === N.ride) || null);
  if (kind === "segment") return JSON.stringify((data.segments || []).find((s) => s.id === N.segment) || null);
  return "";
}

function load(ctx, repaint, data) {
  const k = cacheKey();
  if (!k) return null;
  const c = N.cache[k];
  if (c && c.stamp === stamp(data) && c.data) return c.data;
  if (c && c.pending) return null;
  N.cache[k] = { pending: true, stamp: stamp(data) };
  const [kind, id] = k.split(":");
  Promise.resolve(ctx.action(kind === "ride" ? "ride_detail" : "segment_detail", { [kind]: String(id) })).then((r) => {
    N.cache[k] = { data: r && r.ok ? r : { missing: true }, stamp: stamp(data) };
    if (cacheKey() === k) repaint();
  }).catch(() => { N.cache[k] = { data: { missing: true }, stamp: stamp(data) }; repaint(); });
  return null;
}

export function render(el, data, ctx) {
  setT(ctx);
  injectStyles();
  el.className = "hb-cycling";
  el.textContent = "";
  clearInterval(el._cyTick);
  const d = data || {};
  N.last = { data: d, ctx };
  const nav = makeNav(el, d, ctx);
  const ui = d.ui || {};
  if (ui.n !== N.seenN) {                        // a view pushed by the brain (or the first paint): one transition
    N.seenN = ui.n;
    const v = ui.view === "segment" && !ui.segment ? "segments" : ui.view || "menu";
    N.view = v; N.ride = ui.ride != null ? ui.ride : null; N.segment = ui.segment != null ? ui.segment : null; N.local = {}; nav.local = N.local;
  }

  if (d.status === "running" && d.current) {
    renderRide(el, d, ctx, nav.repaint);
    reportShown(ctx, d, "recording", "");
    return;
  }
  if (S.session) stopSensors();
  if (N.view === "recording") N.view = "menu";

  let shown = "";
  const kind = needs(N.view);
  const det = kind ? load(ctx, nav.repaint, d) : null;
  if (kind && !det) {
    el.appendChild(txt("div", "hb-empty-state", tt("loading", null, "Loading…")));
  } else if (det && det.missing) {
    el.appendChild(crumbs([{ label: tt("crumb_menu", null, "Cycling"), go: () => nav.go("menu") }, { label: dash }]));
    el.appendChild(txt("div", "hb-empty-state", tt("not_found", null, "It is no longer there.")));
  } else if (N.view === "ride") { renderDetail(el, det, ctx, nav); shown = det.ride.name || String(det.ride.started_at || "").slice(0, 10); }
  else if (N.view === "editor") { renderEditor(el, det, ctx, nav); shown = det.ride.name || String(det.ride.started_at || "").slice(0, 10); }
  else if (N.view === "segment") { renderSegment(el, det, ctx, nav); shown = det.segment.name || ""; }
  else if (N.view === "segments") renderPicker(el, d, ctx, nav);
  else if (N.view === "ranking") { renderRanking(el, d, ctx, nav); shown = (N.local.ranking || {}).name || ""; }
  else if (N.view === "history") renderHistory(el, d, ctx, nav);
  else renderMenu(el, d, ctx, nav);
  enrich(d, ctx);
  reportShown(ctx, d, N.view === "ranking" ? "segment" : N.view, shown);
}

// ── The menu ─────────────────────────────────────────────────────────────────────────────────────────────────────

function zonePanel(el, d, ctx) {
  const z = d.zone || {}, def = z.defaults || {};
  const p = txt("div", "hb-panel cy-panel");
  p.appendChild(txt("div", "hb-panel-title", tt("zone_title", null, "Target heart-rate zone")));
  p.appendChild(txt("div", "cy-note cy-left", tt("zone_sub", { age: z.age || 30, max: def.hr_max || dash }, "Age {age} · HR max {max} bpm")));
  const row = txt("div", "cy-zone-row");
  const num = (val, label, key) => {
    const f = txt("label", "hb-field cy-zfield");
    f.appendChild(txt("span", "hb-label", label));
    const i = document.createElement("input");
    i.className = "hb-input"; i.type = "number"; i.inputMode = "numeric"; i.value = val != null ? String(val) : "";
    i.onchange = () => { const v = parseInt(i.value, 10); if (v) ctx.action("set_zone", { [key]: v }); };
    f.appendChild(i);
    return f;
  };
  row.appendChild(num(z.min, tt("zone_min", null, "Min"), "min"));
  row.appendChild(num(z.max, tt("zone_max", null, "Max"), "max"));
  row.appendChild(num(z.age, tt("age", null, "Age"), "age"));
  p.appendChild(row);
  const pre = txt("div", "cy-chips");
  [["z2", tt("z2", null, "Z2 Endurance")], ["z3", tt("z3", null, "Z3 Tempo")], ["z4", tt("z4", null, "Z4 Threshold")]].forEach(([k, label]) => {
    const on = def[k] && def[k].min === z.min && def[k].max === z.max;
    pre.appendChild(btn("hb-btn hb-btn--sm " + (on ? "hb-btn--primary" : "hb-btn--secondary"), label, () => ctx.action("set_zone", { zone: k })));
  });
  p.appendChild(pre);
  el.appendChild(p);
}

const READY_CODES = {
  stable: (p) => tt("w_stable", p, "{temp}° stable ({hours}h)"), rain_now: () => tt("w_rain_now", null, "Raining now"),
  rain_likely: (p) => tt("w_rain_likely", p, "Rain {pct}% ({hours}h)"), heat: (p) => tt("w_heat", p, "Heat {temp}° within {hours}h"),
  heat_uv: (p) => tt("w_heat_uv", p, "Heat + UV {uv}"), rain_possible: (p) => tt("w_rain_possible", p, "Rain possible {pct}%"),
  warming: (p) => tt("w_warming", p, "{now}°→{max}° within {hours}h"), cold: (p) => tt("w_cold", p, "Cold {temp}°"),
  no_data: () => tt("w_no_data", null, "No data"), no_place: () => tt("w_no_place", null, "No place yet"),
  model_unavailable: () => tt("not_yet", null, "Not available yet"),
};

function readyPanel(el, d, ctx) {
  const r = d.readiness;
  const fresh = r && r.computed_at && Date.now() - new Date(r.computed_at).getTime() < 30 * 60 * 1000;
  if (!fresh && !N.readyAsked) { N.readyAsked = true; Promise.resolve(ctx.action("readiness", {})).catch(() => {}); }
  const p = txt("div", "hb-panel cy-panel");
  const h = txt("div", "cy-title-row");
  h.appendChild(txt("div", "hb-panel-title", tt("ready_q", null, "Ready to ride?")));
  h.appendChild(btn("hb-iconbtn", "↻", async () => {
    let loc = {};
    try { const dev = await ctx.device(); const l = await dev.location({ precise: false }); if (l && !l.error) loc = { lat: l.lat, lng: l.lon }; } catch (_) {}
    ctx.action("readiness", { force: true, ...loc });
  }, tt("refresh", null, "Check again")));
  p.appendChild(h);
  if (!r) { p.appendChild(txt("div", "cy-note", tt("evaluating", null, "Checking…"))); el.appendChild(p); return; }
  const grid = txt("div", "cy-ready");
  [["muscle", tt("legs", null, "Legs")], ["nutrition", tt("food", null, "Food")], ["weather", tt("weather", null, "Weather")]].forEach(([k, label]) => {
    const it = r[k] || { level: "gray", code: "no_data" };
    const c = txt("div", "cy-ready-cell");
    c.appendChild(light(it.level));
    c.appendChild(txt("div", "cy-ready-t", label));
    c.appendChild(txt("div", "cy-ready-l", (READY_CODES[it.code] || (() => dash))(it.params || {})));
    grid.appendChild(c);
  });
  p.appendChild(grid);
  el.appendChild(p);
}

async function pickStrap(ctx, box) {
  const dev = await ctx.device();
  box.textContent = "";
  box.appendChild(txt("div", "cy-note", tt("looking", null, "Looking for your strap… put it on and wake it.")));
  const r = await dev.heartRateStraps(8);
  box.textContent = "";
  if (r.error || !r.straps.length) { box.appendChild(txt("div", "cy-note", tt("no_strap", null, "No heart-rate strap found. Check it is on, or that your watch is broadcasting heart rate."))); return; }
  for (const s of r.straps) {
    box.appendChild(btn("hb-btn hb-btn--secondary", s.name, async () => {
      await r.pick(s.id); box.textContent = "";
      box.appendChild(txt("div", "cy-note", tt("strap_saved", { name: s.name }, "{name} will be used for your heart rate.")));
    }));
  }
}

function rideRow(r, ctx, nav, full) {
  const row = txt("div", "hb-card hb-card--interactive cy-ride");
  const open = btn("cy-rowbtn", null, () => nav.go("ride", { ride: r.id }));
  const top = txt("div", "cy-row-top");
  top.appendChild(txt("b", null, r.name || date(r.started_at, { weekday: "short", day: "numeric", month: "short" })));
  if (r.locality) top.appendChild(txt("span", "cy-muted", "· " + r.locality));
  if (r.status === "active") top.appendChild(txt("span", "hb-badge hb-badge--accent", tt("active", null, "active")));
  open.appendChild(top);
  const bits = [fmtKm(r.distance_km || 0) + " km", fmtSec(r.duration_sec || 0)];
  if (r.avg_speed_kmh) bits.push(Number(r.avg_speed_kmh).toFixed(1) + " km/h");
  if (full) bits.push(tt("hr_line", { avg: r.avg_hr || dash, max: r.max_hr || dash }, "HR avg {avg} · max {max}"));
  open.appendChild(txt("div", "cy-muted", bits.join(" · ")));
  row.appendChild(open);
  if (r.status !== "active") row.appendChild(confirmBtn("hb-iconbtn hb-iconbtn--danger", "🗑", () => ctx.action("delete_ride", { ride: String(r.id) }), tt("delete_ride", null, "Delete ride")));
  return row;
}

function renderMenu(el, d, ctx, nav) {
  zonePanel(el, d, ctx);
  const start = btn("hb-btn hb-btn--primary cy-start", tt("start", null, "▶ START RIDE"), async () => {
    // Pre-flight, as the source did: without GPS a ride is useless, so say so instead of starting one.
    try {
      const dev = await ctx.device(); const info = await dev.details();
      if (!(info && info.sensors && info.sensors.location && info.sensors.location.available)) { N.local.noGps = true; nav.repaint(); return; }
    } catch (_) {}
    S.tapped = true; ctx.action("start", {});
  });
  el.appendChild(start);
  if (N.local.noGps) el.appendChild(txt("div", "cy-note cy-warn", tt("no_gps_here", null, "This screen has no GPS: start the ride from the phone.")));
  readyPanel(el, d, ctx);

  const cols = txt("div", "cy-cols");
  const rides = txt("div", "hb-panel cy-panel");
  const rh = txt("div", "cy-title-row");
  rh.appendChild(txt("div", "hb-panel-title", tt("rides", null, "Rides")));
  if ((d.rides || []).length > 6) rh.appendChild(btn("hb-btn hb-btn--ghost hb-btn--sm", tt("see_all", null, "See all →"), () => nav.go("history")));
  rides.appendChild(rh);
  for (const r of (d.rides || []).slice(0, 6)) rides.appendChild(rideRow(r, ctx, nav, false));
  if (!(d.rides || []).length) rides.appendChild(txt("div", "cy-note", tt("no_rides", null, "No rides yet. Press Start ride.")));
  cols.appendChild(rides);

  const segs = txt("div", "hb-panel cy-panel");
  const sh = txt("div", "cy-title-row");
  sh.appendChild(txt("div", "hb-panel-title", tt("segments", null, "Segments")));
  sh.appendChild(btn("hb-btn hb-btn--ghost hb-btn--sm", tt("create", null, "+ Create"), () => { N.local.redoSeg = null; nav.go("segments"); }));
  segs.appendChild(sh);
  const grid = txt("div", "cy-seggrid");
  for (const s of d.segments || []) {
    const c = btn("hb-card hb-card--interactive cy-segcard", null, () => nav.go("segment", { segment: s.id }));
    c.appendChild(txt("b", "cy-segcard-t", s.name || tt("segment", null, "Segment")));
    const v = txt("div", "cy-segcard-v");
    v.appendChild(txt("span", null, ((s.distance_m || 0) / 1000).toFixed(2) + " km"));
    v.appendChild(txt("span", null, tt("pr", null, "PR") + " " + (s.pr_time_sec ? fmtSec(s.pr_time_sec) : dash)));
    v.appendChild(txt("span", null, tt("tries", { n: s.attempts || 0 }, "{n} tries")));
    c.appendChild(v);
    grid.appendChild(c);
  }
  segs.appendChild(grid);
  if (!(d.segments || []).length) segs.appendChild(txt("div", "cy-note", tt("no_segments", null, "No segments yet: create one from a ride.")));
  cols.appendChild(segs);
  el.appendChild(cols);

  const strap = txt("div", "hb-panel cy-panel");
  strap.appendChild(txt("div", "hb-panel-title", tt("strap", null, "Heart-rate strap")));
  const box = txt("div", "cy-chips");
  strap.appendChild(box);
  Promise.resolve(ctx.device()).then((dev) => dev.details()).then((i) => {
    if (i && i.sensors && i.sensors.heart_rate && i.sensors.heart_rate.available) box.appendChild(btn("hb-btn hb-btn--secondary", tt("connect_strap", null, "Choose strap"), () => pickStrap(ctx, box)));
    else box.appendChild(txt("div", "cy-note", tt("strap_phone", null, "The strap connects through the phone app.")));
  }).catch(() => {});
  el.appendChild(strap);
}

function renderHistory(el, d, ctx, nav) {
  el.appendChild(crumbs([{ label: tt("crumb_menu", null, "Cycling"), go: () => nav.go("menu") }, { label: tt("rides", null, "Rides") }]));
  const list = txt("div", "cy-list");
  for (const r of d.rides || []) list.appendChild(rideRow(r, ctx, nav, true));
  if (!(d.rides || []).length) list.appendChild(txt("div", "hb-empty-state", tt("no_rides_yet", null, "No rides recorded yet.")));
  el.appendChild(list);
}

// The town each ride started in and the temperature it was ridden in, filled one ride at a time.
function enrich(d, ctx) {
  if (N.enriching || N.enrichCount >= 12) return;
  const r = (d.rides || []).find((x) => x.start_lat != null && x.status === "done" &&
    ((!x.locality && !x.locality_tried) || (x.weather_temp_c == null && !x.temp_tried)));
  if (!r) return;
  N.enriching = true; N.enrichCount++;
  Promise.resolve(ctx.action("enrich", { ride: String(r.id), lang: (ctx && ctx.lang) || "en" })).catch(() => {})
    .finally(() => { N.enriching = false; });
}

// V2-884 — what the card SHOWS, said through the host's one door after every paint: whether a ride runs and where it
// is recorded, which screen is open and the ride or segment on it.
function reportShown(ctx, d, view, shown) {
  if (!ctx || typeof ctx.state !== "function") return;
  const cur = d.status === "running" ? d.current : null;
  const phase = !cur ? "idle" : Date.now() < cur.countdown_until_ms ? "countdown" : cur.paused ? "paused" : "running";
  const views = ["menu", "history", "ride", "segments", "segment", "editor", "recording"];
  try { Promise.resolve(ctx.state({ phase, recorder: recorderOf(cur), view: views.includes(view) ? view : "menu",
    shown: String(shown || "").slice(0, 40) }, { applied: true, of: d })).catch(() => {}); } catch (_) {}
}
