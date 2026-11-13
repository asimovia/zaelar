// Cycling — the ride being recorded. ONE screen reads the sensors (the one that claims the ride: the phone app, or
// the screen where he tapped Start); every other screen shows the same figures from data.py. In the phone app the
// reading goes on with the screen locked (ctx.device().activity()) and the missed samples arrive in one batch.
// Three panes, as in the source: control (speed, time, distance, heart rate against his zone), map, ghost.

import { tt, txt, btn, dash, fmtSec, fmtKm, fmtDelta, stat } from "./util.js";
import { tileMap, along } from "./map.js";
import * as G from "./ghost.js";

// The sensor session of THIS screen (module state: it outlives the re-renders every data push causes).
export const S = { owner: "s-" + Math.random().toString(36).slice(2) + Date.now().toString(36), session: null,
  starting: false, queue: [], flush: null, tapped: false, ctx: null, error: null, failedFor: null,
  pane: "control", zoom: "mid", endPrompt: null, seenEv: null, toast: null, ghostMap: false, picker: false };

async function flush() {
  if (!S.queue.length || !S.ctx) return;
  const batch = S.queue.splice(0, S.queue.length);
  const r = await S.ctx.action("samples", { owner: S.owner, samples: batch });
  if (!r || (!r.ok && !r.owned_by_another_screen)) S.queue.unshift(...batch);   // retried on the next beat
}

export async function stopSensors() {
  const s = S.session; S.session = null;
  if (s && s.stop) await s.stop();
  await flush();
  clearInterval(S.flush); S.flush = null;
}

// Started ONLY for a ride he began: his tap here, or — in the phone app — his request (the app he carries).
async function ensureSensors(cur, ctx, repaint) {
  if (S.session || S.starting || S.failedFor === cur.id) return;
  if (cur.owner && cur.owner !== S.owner) return;
  S.starting = true;
  try {
    const dev = await ctx.device();
    const info = await dev.details();
    if (!cur.owner && !S.tapped && !info.background_sessions) return;
    const c = await ctx.action("claim", { owner: S.owner });
    if (!c || !c.ok) return;
    const has = (k) => info.sensors && info.sensors[k] && info.sensors[k].available;
    const sensors = ["location", "heart_rate", "altitude"].filter(has);
    const r = await dev.activity({ sensors: sensors.length ? sensors : ["location"], label: "", kind: "cycling" },
      (sample) => S.queue.push(sample));
    if (r.error) { S.error = r.error; S.failedFor = cur.id; } else { S.session = r; S.error = null; S.flush = setInterval(flush, 5000); }
    S.starting = false;
    repaint();
  } finally { S.starting = false; S.tapped = false; }
}

export function recorderOf(cur) {
  if (!cur) return "none";
  return cur.owner && cur.owner === S.owner && S.session ? "here" : cur.owner && cur.owner !== S.owner ? "elsewhere" : "none";
}

function eventText(e) {
  const n = e.name || "";
  switch (e.kind) {
    case "enter": return tt("ev_enter", { name: n }, "Entering: {name}");
    case "approach": return tt("ev_approach", { name: n }, "Approaching: {name}");
    case "abandon": return tt("ev_abandon", { name: n }, "You left {name} · segment void");
    case "finish": {
      const base = tt("ev_finish", { name: n, time: fmtSec(e.time_sec) }, "Finished {name}: {time}");
      if (e.delta_sec == null) return base;
      return base + " " + (e.delta_sec < 0 ? tt("ev_pr", { d: fmtSec(-e.delta_sec) }, "PR (−{d})") : "(+" + fmtSec(e.delta_sec) + ")");
    }
    case "gap_rebuilt": return tt("ev_gap", { km: e.km, n: e.points }, "Lost stretch rebuilt: {km} km · {n} points");
    case "gap_straight": return tt("ev_gap_straight", { km: e.km }, "GPS gap (no road found): +{km} km straight");
    default: return "";
  }
}

function speedFig(v, cls) {
  const f = txt("div", cls);
  const n = Math.max(0, Number(v) || 0);
  f.appendChild(txt("span", "cy-sp-int", String(Math.floor(n))));
  f.appendChild(txt("span", "cy-sp-dec", "." + Math.floor((n * 10) % 10)));
  return f;
}

export function renderRide(el, d, ctx, repaint) {
  S.ctx = ctx;
  const cur = d.current;
  ensureSensors(cur, ctx, repaint);
  const now = Date.now();
  const tick = [];                                // what moves every second without a data push

  // ── overlays: the GPS countdown, the end-of-ride question ──
  if (now < cur.countdown_until_ms) {
    const ov = txt("div", "cy-overlay");
    ov.appendChild(txt("div", "cy-ov-lbl", tt("calibrating", null, "Calibrating GPS")));
    const num = txt("div", "cy-ov-num", String(Math.ceil((cur.countdown_until_ms - now) / 1000)));
    ov.appendChild(num);
    ov.appendChild(txt("div", "cy-ov-hint", tt("dont_move", null, "Don't move until it starts")));
    el.appendChild(ov);
    tick.push(() => { const s = Math.ceil((cur.countdown_until_ms - Date.now()) / 1000); if (s <= 0) repaint(); else num.textContent = String(s); });
  }
  if (S.endPrompt) {
    const ov = txt("div", "cy-overlay");
    if (S.endPrompt === "main") {
      ov.appendChild(txt("div", "cy-ov-q", tt("save_q", null, "Save the ride?")));
      ov.appendChild(btn("hb-btn hb-btn--primary cy-big", tt("save", null, "SAVE"), async () => { S.endPrompt = null; await stopSensors(); ctx.action("stop", {}); }));
      ov.appendChild(btn("hb-btn hb-btn--danger cy-big", tt("discard", null, "DISCARD"), () => { S.endPrompt = "confirm"; repaint(); }));
      ov.appendChild(btn("hb-btn hb-btn--ghost", tt("keep_riding", null, "Keep riding"), () => { S.endPrompt = null; repaint(); }));
    } else {
      ov.appendChild(txt("div", "cy-ov-q", tt("discard_q", null, "Are you sure you want to discard it?")));
      ov.appendChild(txt("div", "cy-ov-hint", tt("discard_sub", null, "The recording will be deleted and cannot be recovered.")));
      ov.appendChild(btn("hb-btn hb-btn--danger hb-btn--solid cy-big", tt("discard_yes", null, "YES, DISCARD"), async () => { S.endPrompt = null; await stopSensors(); ctx.action("discard", {}); }));
      ov.appendChild(btn("hb-btn hb-btn--secondary cy-big", tt("discard_no", null, "NO, GO BACK"), () => { S.endPrompt = "main"; repaint(); }));
    }
    el.appendChild(ov);
  }

  // ── events (entering a segment, a PR, a rebuilt gap): each one said once on this screen ──
  const evs = cur.events || [];
  const maxN = evs.length ? evs[evs.length - 1].n : 0;
  if (S.seenEv === null || S.seenEv.ride !== cur.id) S.seenEv = { ride: cur.id, n: maxN };   // never replay the past
  const fresh = evs.filter((e) => e.n > S.seenEv.n);
  if (fresh.length) { S.seenEv.n = maxN; S.toast = { text: fresh.map(eventText).filter(Boolean).join(" · "), until: now + 5000 }; }
  if (S.toast && S.toast.until > now) {
    const t = txt("div", "cy-toast", S.toast.text); t.setAttribute("role", "status"); el.appendChild(t);
  }

  // ── where it is recorded ──
  const rec = recorderOf(cur);
  const where = rec === "here" ? (S.session.background ? tt("here_locked", null, "Recording on this phone — it keeps going with the screen locked.")
    : tt("here", null, "Recording on this screen — keep it open."))
    : rec === "elsewhere" ? tt("elsewhere", null, "Recording on your other screen.")
      : S.error ? tt("no_sensors", { why: S.error }, "This screen cannot read the GPS ({why}).")
        : tt("waiting", null, "Waiting for the screen that records it.");
  el.appendChild(txt("div", "cy-note", where));

  const tabs = txt("div", "hb-tabs cy-tabs");
  [["control", tt("pane_control", null, "Ride")], ["map", tt("pane_map", null, "Map")], ["ghost", tt("pane_ghost", null, "Ghost")]].forEach(([k, label]) => {
    const inside = k === "ghost" && (cur.ghost.inside || []).length;
    const b = btn("hb-tab" + (S.pane === k ? " is-on" : "") + (inside ? " cy-blink" : ""), label, () => { S.pane = k; repaint(); });
    tabs.appendChild(b);
  });
  el.appendChild(tabs);

  const elapsedNow = () => cur.paused || now < cur.countdown_until_ms ? cur.elapsed_s
    : cur.elapsed_s + Math.max(0, Math.floor((Date.now() - now) / 1000));
  if (S.pane === "control") paneControl(el, cur, ctx, repaint, tick, elapsedNow);
  else if (S.pane === "map") paneMap(el, cur, repaint, tick, elapsedNow);
  else paneGhost(el, cur, ctx, repaint, tick, d.segments || []);

  clearInterval(el._cyTick);
  if (tick.length) el._cyTick = setInterval(() => { if (!el.isConnected) { clearInterval(el._cyTick); return; } tick.forEach((f) => f()); }, 1000);
}

function endButtons(el, cur, ctx, repaint) {
  const row = txt("div", "cy-row2");
  row.appendChild(btn("hb-btn hb-btn--secondary cy-big", cur.paused ? tt("resume", null, "▶ RESUME") : tt("pause", null, "⏸ PAUSE"),
    () => ctx.action(cur.paused ? "resume" : "pause", {})));
  row.appendChild(btn("hb-btn hb-btn--danger cy-big", tt("end", null, "■ FINISH"), () => { S.endPrompt = "main"; repaint(); }));
  el.appendChild(row);
}

function ghostBanner(el, cur, tick) {
  const a = cur.ghost.active;
  if (!a) return;
  const b = txt("div", "cy-ghost-banner");
  b.appendChild(txt("span", "cy-gb-name", a.name || ""));
  const tm = txt("span", "cy-gb-time", fmtSec((Date.now() - a.entered_ms) / 1000));
  b.appendChild(tm);
  let dl = null;
  if (a.pr_time_sec) {
    b.appendChild(txt("span", "cy-gb-pr", tt("pr_short", { t: fmtSec(a.pr_time_sec) }, "PR {t}")));
    dl = txt("span", "cy-gb-delta"); b.appendChild(dl);
  }
  const upd = () => {
    const sec = (Date.now() - a.entered_ms) / 1000;
    tm.textContent = fmtSec(sec);
    if (dl) { const dd = Math.round(sec - a.pr_time_sec); dl.textContent = (dd < 0 ? "−" : "+") + fmtSec(Math.abs(dd)); dl.className = "cy-gb-delta " + (dd < 0 ? "is-ahead" : "is-behind"); }
  };
  upd(); tick.push(upd);
  el.appendChild(b);
}

function paneControl(el, cur, ctx, repaint, tick, elapsedNow) {
  ghostBanner(el, cur, tick);
  const big = txt("div", "cy-speed");
  big.appendChild(txt("div", "cy-stat-lbl", tt("speed_kmh", null, "SPEED (km/h)")));
  big.appendChild(speedFig(cur.speed_kmh, "cy-speed-val"));
  if (cur.paused) big.appendChild(txt("div", "cy-note", tt("paused", null, "⏸ paused")));
  el.appendChild(big);
  const grid = txt("div", "cy-grid");
  grid.appendChild(stat(cur.avg_speed_kmh != null ? cur.avg_speed_kmh.toFixed(2) : dash, tt("avg_kmh", null, "AVG (km/h)")));
  grid.appendChild(stat(cur.max_speed_kmh > 0 ? cur.max_speed_kmh.toFixed(2) : dash, tt("max_kmh", null, "MAX (km/h)")));
  const tStat = stat(fmtSec(elapsedNow()), tt("time", null, "TIME"));
  grid.appendChild(tStat);
  tick.push(() => { tStat.lastChild.textContent = fmtSec(elapsedNow()); });
  grid.appendChild(stat(cur.has_location ? fmtKm(cur.distance_km) + " km" : dash, tt("dist", null, "DIST")));
  grid.appendChild(stat(cur.altitude_m != null ? Math.round(cur.altitude_m) + " m" : dash, tt("alt", null, "ALT")));
  el.appendChild(grid);

  // The heart rate against his zone: a number, a bar, a word — never the colour alone; no strap is no reading.
  const hr = txt("div", "cy-hr cy-zone-" + cur.zone_status);
  const top = txt("div", "cy-hr-top");
  top.appendChild(txt("span", "cy-hr-num", cur.heart_rate != null ? String(cur.heart_rate) : dash));
  top.appendChild(txt("span", "cy-hr-unit", cur.heart_rate != null ? tt("bpm", null, "bpm")
    : cur.has_heart_rate ? tt("hr_waiting", null, "strap not sending") : tt("hr_none", null, "no heart-rate strap")));
  hr.appendChild(top);
  const bar = txt("div", "cy-zbar");
  const mark = txt("i", "cy-zmark");
  mark.style.left = (50 + G.zonePosition(cur.heart_rate, cur.zone.min, cur.zone.max) * 20) + "%";
  bar.appendChild(txt("b", "cy-zband"));
  if (cur.heart_rate != null) bar.appendChild(mark);
  hr.appendChild(bar);
  const word = { in: tt("zone_in", null, "in zone"), below: tt("zone_below", null, "push harder"), above: tt("zone_above", null, "ease off") }[cur.zone_status] || dash;
  hr.appendChild(txt("div", "cy-note", tt("zone_line", { min: cur.zone.min, max: cur.zone.max, word }, "zone {min}–{max} · {word}")));
  el.appendChild(hr);
  endButtons(el, cur, ctx, repaint);
}

function paneMap(el, cur, repaint, tick, elapsedNow) {
  const zooms = txt("div", "hb-tabs cy-tabs");
  [["far", tt("zoom_far", null, "Far"), 13], ["mid", tt("zoom_mid", null, "Mid"), 15], ["near", tt("zoom_near", null, "Near"), 18]].forEach(([k, label]) => {
    zooms.appendChild(btn("hb-tab" + (S.zoom === k ? " is-on" : ""), label, () => { S.zoom = k; repaint(); }));
  });
  el.appendChild(zooms);
  const box = txt("div", "cy-mapbox cy-mapbox-live");
  el.appendChild(box);
  const z = { far: 13, mid: 15, near: 18 }[S.zoom] || 15;
  tileMap(box, { lines: [{ pts: cur.route, cls: "cy-route" }], dots: cur.last ? [{ at: cur.last, cls: "cy-me", r: 8 }] : [],
    follow: cur.last ? { at: cur.last, z } : null, fitTo: cur.route }, "live:" + S.zoom + ":" + (cur.last || []).join(","));
  const grid = txt("div", "cy-grid");
  grid.appendChild(stat(String(Math.round(cur.speed_kmh || 0)), tt("speed_short", null, "KM/H")));
  grid.appendChild(stat(cur.heart_rate != null ? String(cur.heart_rate) : dash, tt("hr_short", null, "♥")));
  grid.appendChild(stat(fmtKm(cur.distance_km), tt("dist", null, "DIST")));
  const tStat = stat(fmtSec(elapsedNow()), tt("time", null, "TIME"));
  grid.appendChild(tStat);
  tick.push(() => { tStat.lastChild.textContent = fmtSec(elapsedNow()); });
  el.appendChild(grid);
  el.appendChild(btn("hb-btn hb-btn--danger cy-big", tt("end_route", null, "■ FINISH RIDE"), () => { S.endPrompt = "main"; repaint(); }));
}

function paneGhost(el, cur, ctx, repaint, tick, segments) {
  const g = cur.ghost;
  if (g.approach) {
    const ap = txt("div", "cy-approach");
    ap.appendChild(txt("b", null, tt("approaching", null, "Approaching")));
    ap.appendChild(txt("span", null, g.approach.name || ""));
    ap.appendChild(txt("span", "cy-approach-d", (g.approach.dist_m || 0) + " m"));
    el.appendChild(ap);
  }
  if (!segments.length) {
    const e = txt("div", "hb-empty-state cy-empty");
    e.appendChild(txt("p", null, tt("ghost_empty", null, "No segments defined yet.")));
    e.appendChild(txt("p", null, tt("ghost_empty_hint", null, "Ride a route a few times, then create segments from your rides.")));
    el.appendChild(e);
    return;
  }
  // The picker: only the segments he is inside right now (they can overlap).
  const pick = txt("div", "cy-picker");
  const inside = g.inside || [];
  const selName = (inside.find((s) => s.id === g.selected) || {}).name;
  const pb = btn("hb-btn hb-btn--secondary cy-picker-btn", selName || (inside.length ? tt("choose_seg", null, "Choose segment") : tt("outside", null, "Not in a segment")),
    () => { if (inside.length) { S.picker = !S.picker; repaint(); } });
  pb.disabled = !inside.length;
  if (inside.length) pb.appendChild(txt("span", "hb-badge hb-badge--accent hb-badge--bare", String(inside.length)));
  pick.appendChild(pb);
  if (S.picker && inside.length) {
    const list = txt("div", "cy-picker-list");
    for (const s of inside) list.appendChild(btn("hb-btn hb-btn--ghost" + (s.id === g.selected ? " is-selected" : ""), s.name || "",
      () => { S.picker = false; ctx.action("ghost_select", { segment: String(s.id) }); }));
    pick.appendChild(list);
  }
  pick.appendChild(btn("hb-btn hb-btn--ghost", S.ghostMap ? tt("hide_map", null, "Hide map") : tt("show_map", null, "Map"), () => { S.ghostMap = !S.ghostMap; repaint(); }));
  el.appendChild(pick);

  const a = g.active;
  const body = txt("div", "cy-ghost");
  el.appendChild(body);
  const draw = () => {
    body.textContent = "";
    if (!a) return;
    const now = Date.now();
    const rivals = G.competitors(g, now);
    const len = txt("div", "cy-seglen" + (G.nearFinish(a, cur.speed_kmh) ? " is-near" : ""));
    const fill = txt("i", "cy-seglen-fill"); fill.style.width = G.progressPct(a) + "%";
    len.appendChild(fill);
    body.appendChild(len);
    const st = txt("div", "cy-staff");
    if (G.beyondAhead(rivals)) st.appendChild(txt("div", "cy-of cy-of-top", "▲ +" + G.beyondAhead(rivals)));
    for (const c of G.staff(rivals)) {
      const r = txt("div", "cy-rival " + (c.is_pr ? "is-pr" : c.dir === "ahead" ? "is-ahead" : "is-behind"));
      r.style.top = c.y + "%"; r.style.left = c.x + "%";
      r.title = c.is_pr ? tt("ghost_pr", null, "PR") : (c.session_name || tt("ride_n", { n: c.session_id }, "Ride {n}"));
      r.appendChild(txt("span", "cy-rival-lbl", (c.deltaSec >= 0 ? "+" : "−") + fmtDelta(c.deltaSec)));
      st.appendChild(r);
    }
    const me = txt("div", "cy-me-mark", tt("me", null, "YOU")); me.style.top = G.myY(rivals) + "%";
    st.appendChild(me);
    if (G.beyondBehind(rivals)) st.appendChild(txt("div", "cy-of cy-of-bot", "▼ +" + G.beyondBehind(rivals)));
    body.appendChild(st);
    const pos = txt("div", "cy-ghost-pos");
    const nb = G.nextBehind(rivals), na = G.nextAhead(rivals);
    pos.appendChild(txt("span", "cy-gp-behind", nb ? "−" + fmtDelta(nb.deltaSec) : dash));
    pos.appendChild(txt("b", "cy-gp-rank", "#" + G.rank(rivals)));
    pos.appendChild(txt("span", "cy-gp-ahead", na ? "+" + fmtDelta(na.deltaSec) : dash));
    body.appendChild(pos);
    const grid = txt("div", "cy-grid");
    grid.appendChild(stat(String((Math.floor((cur.speed_kmh || 0) * 10) / 10).toFixed(1)), tt("speed_short", null, "KM/H")));
    grid.appendChild(stat(cur.avg_speed_kmh != null ? cur.avg_speed_kmh.toFixed(1) : dash, tt("avg_short", null, "AVG · km/h")));
    grid.appendChild(stat(fmtSec((now - a.entered_ms) / 1000), tt("in_seg", null, "IN SEGMENT")));
    grid.appendChild(stat(G.fmtDist(G.distInSeg(a)), tt("seg_dist", null, "SEG. DIST")));
    body.appendChild(grid);
  };
  draw(); tick.push(draw);
  if (!a) body.appendChild(txt("div", "cy-note", tt("ghost_wait", null, "The ghost appears when you enter a segment.")));

  if (S.ghostMap) {
    const box = txt("div", "cy-mapbox");
    el.appendChild(box);
    const sel = g.segment;
    const segPts = sel ? ((g.pr_polyline_of === sel.id && g.pr_polyline) || [[sel.start_lat, sel.start_lng], [sel.end_lat, sel.end_lng]]) : null;
    const lines = (g.nearby || []).filter((n) => !sel || n.id !== sel.id).map((n) => ({ pts: n.polyline, cls: "cy-nearby" }));
    if (segPts) lines.push({ pts: segPts, cls: (g.inside || []).some((s) => sel && s.id === sel.id) ? "cy-seg-in" : "cy-seg" });
    const dots = [];
    if (sel) { dots.push({ at: [sel.start_lat, sel.start_lng], cls: "cy-start" }, { at: [sel.end_lat, sel.end_lng], cls: "cy-end" }); }
    if (a && segPts) for (const c of G.competitors(g, Date.now())) {
      const p = along(segPts, Math.min(1, Math.max(0, ((Date.now() - a.entered_ms) / 1000) / c.time_sec)));
      if (p) dots.push({ at: p, cls: c.deltaSec < 0 ? "cy-rv-behind" : "cy-rv-ahead", label: c.is_pr ? tt("ghost_pr", null, "PR") : (c.session_name || "") });
    }
    if (cur.last) dots.push({ at: cur.last, cls: "cy-me", r: 9 });
    const fitPts = [...(segPts || []), ...dots.map((d) => d.at)];
    tileMap(box, { lines, dots, fitTo: fitPts.length >= 2 ? fitPts : null, follow: fitPts.length < 2 && cur.last ? { at: cur.last, z: 16 } : null },
      "ghost:" + (sel ? sel.id : "") + ":" + (cur.last || []).join(","));
  }
}
