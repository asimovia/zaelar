// Activity — a ride, a run, a walk or a drive the person starts (V2-890 F1).
// ONE screen reads the sensors (the one that claims the activity: the phone app, or the screen where he tapped
// Start); every other screen shows the same figures live from data.py. In the phone app the reading goes on with
// the screen locked (ctx.device().activity()) and the missed samples arrive in one batch when it comes back.

function injectStyles() {
  if (document.getElementById("hb-activity-css")) return;
  const s = document.createElement("style"); s.id = "hb-activity-css"; s.textContent = `
  .hb-activity{font-family:var(--sans,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif);
    width:100%;min-height:100%;box-sizing:border-box;display:flex;flex-direction:column;gap:14px;
    color:var(--hb-ink,#F2F4F7)}
  .hb-activity .ac-kinds{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
  .hb-activity .ac-btn{font-family:inherit;font-size:var(--fs-body,.9375rem);font-weight:600;min-height:52px;border-radius:14px;cursor:pointer;
    border:1px solid var(--hb-line,rgba(255,255,255,.14));background:var(--hb-bg-soft,#272D35);color:var(--hb-ink,#F2F4F7);
    transition:border-color var(--hb-t-fast,120ms),background var(--hb-t-fast,120ms)}
  .hb-activity .ac-btn:hover{border-color:var(--hb-accent,#AE90FF);color:var(--hb-accent,#AE90FF)}
  .hb-activity .ac-btn:active{background:var(--hb-hover,#3C434F)}
  .hb-activity .ac-btn:focus-visible,.hb-activity .ac-row:focus-visible{outline:none;box-shadow:var(--hb-focus-ring,0 0 0 2px #AE90FF)}
  .hb-activity .ac-btn:disabled{opacity:.5;cursor:default;border-color:var(--hb-line,rgba(255,255,255,.14));color:var(--hb-muted,#A3ADBD)}
  .hb-activity .ac-stop{background:var(--hb-risk,#FF7384);border-color:var(--hb-risk,#FF7384);color:var(--canvas,#16191E)}
  .hb-activity .ac-stop:hover{color:var(--canvas,#16191E);border-color:var(--hb-ink,#F2F4F7)}
  .hb-activity .ac-hr{display:flex;align-items:baseline;justify-content:center;gap:8px}
  .hb-activity .ac-hr b{font-size:4.5rem;font-weight:700;line-height:1;font-variant-numeric:tabular-nums;color:var(--hb-risk,#FF7384)}
  .hb-activity .ac-hr span{font-size:var(--fs-ui,.875rem);color:var(--hb-muted,#A3ADBD)}
  .hb-activity .ac-spark{width:100%;height:36px;display:block}
  .hb-activity .ac-spark polyline{fill:none;stroke:var(--hb-risk,#FF7384);stroke-width:1.5;stroke-linejoin:round;stroke-linecap:round;vector-effect:non-scaling-stroke}
  .hb-activity .ac-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
  .hb-activity .ac-fig{background:var(--hb-bg-soft,#272D35);border-radius:12px;padding:10px 12px}
  .hb-activity .ac-fig b{display:block;font-size:1.625rem;font-weight:600;font-variant-numeric:tabular-nums}
  .hb-activity .ac-fig span{font-size:var(--fs-micro,.75rem);color:var(--hb-muted,#A3ADBD);text-transform:uppercase;letter-spacing:.05em}
  .hb-activity .ac-note{font-size:var(--fs-caption,.8125rem);color:var(--hb-muted,#A3ADBD);text-align:center}
  .hb-activity .ac-route{width:100%;height:160px;background:var(--hb-bg-soft,#272D35);border-radius:12px}
  .hb-activity .ac-route polyline{fill:none;stroke:var(--hb-accent,#AE90FF);stroke-width:3;stroke-linejoin:round;stroke-linecap:round}
  .hb-activity .ac-strap{display:flex;align-items:center;justify-content:space-between;gap:10px;font-size:var(--fs-ui,.875rem)}
  .hb-activity .ac-strap .ac-btn{min-height:40px;padding:0 14px;font-size:var(--fs-ui,.875rem)}
  .hb-activity .ac-strap span{color:var(--hb-muted,#A3ADBD)}
  .hb-activity .ac-week{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:6px;align-items:end;height:72px}
  .hb-activity .ac-day{display:flex;flex-direction:column;align-items:center;justify-content:flex-end;gap:4px;height:100%}
  .hb-activity .ac-day i{display:block;width:70%;min-height:2px;border-radius:4px 4px 0 0;background:var(--hb-accent,#AE90FF)}
  .hb-activity .ac-day i.ac-nil{background:var(--hb-neutral,#4A5260)}
  .hb-activity .ac-day span{font-size:var(--fs-micro,.75rem);color:var(--hb-muted,#A3ADBD)}
  .hb-activity .ac-hist{display:flex;flex-direction:column;gap:6px}
  .hb-activity .ac-row{display:flex;justify-content:space-between;gap:8px;font:inherit;font-size:var(--fs-ui,.875rem);padding:8px 0;
    border:0;border-bottom:1px solid var(--hb-line,rgba(255,255,255,.14));background:none;color:inherit;text-align:left;cursor:pointer;width:100%}
  .hb-activity .ac-row:hover b{color:var(--hb-accent,#AE90FF)}
  .hb-activity .ac-row span{color:var(--hb-muted,#A3ADBD)}
  .hb-activity .ac-detail{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:8px;padding:4px 0 8px}
  .hb-activity h4{margin:4px 0 0;font-size:var(--fs-caption,.8125rem);font-weight:600;color:var(--hb-muted,#A3ADBD);text-transform:uppercase;letter-spacing:.06em}
  `; document.head.appendChild(s);
}

let _T = null;
function tt(key, params, fb) {
  try { if (_T) { const s = _T("widgets.activity." + key, params); if (s && s !== "widgets.activity." + key) return s; } } catch (_) {}
  let s = fb;
  if (params) for (const k in params) s = s.split("{" + k + "}").join(String(params[k]));
  return s;
}
function txt(tag, cls, s) { const e = document.createElement(tag); if (cls) e.className = cls; if (s != null) e.textContent = s; return e; }
function kindLabel(k) {
  return ({ cycling: tt("kind_cycling", null, "Ride"), running: tt("kind_running", null, "Run"),
    walking: tt("kind_walking", null, "Walk"), driving: tt("kind_driving", null, "Drive") })[k] || k;
}
function clock(sec) {
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return (h ? h + ":" + String(m).padStart(2, "0") : String(m)) + ":" + String(s).padStart(2, "0");
}
const dash = "—";
let _lang;
// Numbers as the person's language writes them («12,4 km» in Spanish, «12.4 km» in English).
function num(v, digits) {
  try { return new Intl.NumberFormat(_lang || undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(v); }
  catch (_) { return Number(v).toFixed(digits); }
}
const km = (m, digits) => num(m / 1000, digits) + " km";
// What a failed sensor start means, in words — never the raw code.
function whyLabel(code) {
  return ({ denied: tt("why_denied", null, "permission denied"), unavailable: tt("why_unavailable", null, "no sensor available"),
    unsupported: tt("why_unsupported", null, "this browser has no sensors for it"), timeout: tt("why_timeout", null, "no answer from the sensor") })[code]
    || tt("why_unavailable", null, "no sensor available");
}

// This screen's token. Kept for the tab's life (sessionStorage), so a reload of the same screen — the phone app's
// web view coming back — is still the screen that owns its activity, and goes on recording instead of orphaning it.
function screenToken() {
  const k = "hb-activity-owner";
  try { const t = sessionStorage.getItem(k); if (t) return t; } catch (_) { /* storage blocked */ }
  const t = "s-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
  try { sessionStorage.setItem(k, t); } catch (_) { /* storage blocked: this tab only */ }
  return t;
}
function strapName() { try { return localStorage.getItem("hb-activity-strap") || ""; } catch (_) { return ""; } }
function keepStrapName(n) { try { localStorage.setItem("hb-activity-strap", n); } catch (_) { /* storage blocked */ } }

// ── The sensor session of THIS screen (module state: it outlives the re-renders every data push causes, and the card
// being closed and reopened — the module stays loaded). ──
const S = { owner: screenToken(), session: null, starting: false, queue: [], flush: null, tapped: false, ctx: null,
  error: null, failedFor: null, want: null, open: null };

async function flush() {
  if (!S.queue.length || !S.ctx) return;
  const batch = S.queue.splice(0, S.queue.length);
  const r = await S.ctx.action("samples", { owner: S.owner, samples: batch });
  if (!r || (!r.ok && !r.owned_by_another_screen)) S.queue.unshift(...batch);   // retried on the next beat
}

async function stopSensors() {
  const s = S.session; S.session = null;
  if (s && s.stop) await s.stop();
  await flush();
  clearInterval(S.flush); S.flush = null;
}

// Started ONLY for an activity he began: his tap here, or — in the phone app — his request, which is the app
// he carries with him. A desktop browser never starts reading because a request was made elsewhere.
// The sensors start FIRST and the claim follows: a screen whose sensors fail never holds the activity, so another
// screen (the phone) can still take it.
async function ensureSensors(d, ctx) {
  const id = d.started_at || 0;
  if (S.session || S.starting || S.failedFor === id) return;   // a failure is not retried for the same activity
  if (d.owner && d.owner !== S.owner) return;
  S.starting = true;
  S.want = id;
  try {
    const dev = await ctx.device();
    const info = await dev.details();
    if (d.owner !== S.owner && !S.tapped && !info.background_sessions) return;
    const has = (k) => info.sensors && info.sensors[k] && info.sensors[k].available;
    const sensors = ["location", "heart_rate", "altitude", "motion_activity"].filter(has);
    const r = await dev.activity({ sensors: sensors.length ? sensors : ["location"], label: d.label || "", kind: d.kind },
      (sample) => S.queue.push(sample));
    if (!r || r.error) { S.error = (r && r.error) || "unavailable"; S.failedFor = id; }
    else if (S.want !== id) { if (r.stop) await r.stop(); }        // the activity ended while the sensors were starting
    else {
      const c = await ctx.action("claim", { owner: S.owner });
      if (!c || !c.ok) { if (r.stop) await r.stop(); }             // another screen took it first: it records, not this one
      else { S.error = null; S.session = r; S.sessionFor = id; S.flush = setInterval(flush, 5000); }
    }
    S.starting = false;
    if (S.repaint) S.repaint();                       // the session started or failed: the card says so now
  } finally { S.starting = false; S.tapped = false; }
}

async function pickStrap(ctx, box, repaint) {
  const dev = await ctx.device();
  if (!dev.heartRateStraps) return;
  box.textContent = "";
  box.appendChild(txt("div", "ac-note", tt("looking", null, "Looking for your strap… put it on and wake it.")));
  const r = await dev.heartRateStraps(8);
  box.textContent = "";
  if (r.error || !r.straps.length) { box.appendChild(txt("div", "ac-note", tt("no_strap", null, "No heart-rate strap found. Check it is on, or that your watch is broadcasting heart rate."))); return; }
  for (const s of r.straps) {
    const b = txt("button", "ac-btn", s.name);
    b.onclick = async () => { await r.pick(s.id); keepStrapName(s.name); box.textContent = ""; box.appendChild(txt("div", "ac-note", tt("strap_saved", { name: s.name }, "{name} will be used for your heart rate."))); setTimeout(repaint, 1500); };
    box.appendChild(b);
  }
}

// The strap this phone uses, as a setting you can see: its name and «Change». Only where a strap can be read.
function strapRow(ctx, repaint) {
  const box = txt("div", "ac-hist");
  ctx.device().then((dev) => dev.details()).then((i) => {
    const hr = i && i.sensors && i.sensors.heart_rate;
    if (!hr || !hr.available) return;
    const row = txt("div", "ac-strap");
    const saved = hr.saved_strap ? (strapName() || tt("strap_saved_unnamed", null, "a saved strap")) : "";
    row.appendChild(txt("span", null, saved ? tt("strap_is", { name: saved }, "Heart rate from {name}") : tt("strap_none", null, "No heart-rate strap chosen")));
    const b = txt("button", "ac-btn", saved ? tt("strap_change", null, "Change") : tt("connect_strap", null, "Heart-rate strap"));
    b.onclick = () => pickStrap(ctx, box, repaint);
    row.appendChild(b);
    box.appendChild(row);
  }).catch(() => {});
  return box;
}

// A screen that cannot record (no location at all): said at rest, before he taps Start and wonders why nothing moves.
function sensorsNote(ctx) {
  const box = txt("div");
  ctx.device().then((dev) => dev.details()).then((i) => {
    const s = (i && i.sensors) || {};
    if (!(s.location && s.location.available) && !(s.heart_rate && s.heart_rate.available))
      box.appendChild(txt("div", "ac-note", tt("no_sensors_here", null, "This screen has no location or heart-rate sensor: start the activity from your phone.")));
  }).catch(() => {});
  return box;
}

function fig(value, label) { const f = txt("div", "ac-fig"); f.appendChild(txt("b", null, value)); f.appendChild(txt("span", null, label)); return f; }

function routeSvg(route) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "ac-route"); svg.setAttribute("viewBox", "0 0 100 60"); svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
  if (route.length < 2) return svg;
  const lats = route.map((p) => p[0]), lons = route.map((p) => p[1]);
  const midLat = (Math.min(...lats) + Math.max(...lats)) / 2, kx = Math.cos(midLat * Math.PI / 180);
  const x0 = Math.min(...lons) * kx, x1 = Math.max(...lons) * kx, y0 = Math.min(...lats), y1 = Math.max(...lats);
  const span = Math.max(x1 - x0, (y1 - y0) * 100 / 60, 1e-6), sc = 90 / span;
  const pts = route.map((p) => [5 + (p[1] * kx - x0) * sc, 55 - (p[0] - y0) * sc].map((v) => v.toFixed(2)).join(",")).join(" ");
  const pl = document.createElementNS("http://www.w3.org/2000/svg", "polyline"); pl.setAttribute("points", pts);
  svg.appendChild(pl);
  return svg;
}

// The live heart rate of the last minutes ([[t_ms, bpm]] from data.py). Nothing drawn without two readings.
function sparkSvg(pts) {
  if (!pts || pts.length < 2) return null;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "ac-spark"); svg.setAttribute("viewBox", "0 0 100 24"); svg.setAttribute("preserveAspectRatio", "none");
  const t0 = pts[0][0], t1 = pts[pts.length - 1][0], b = pts.map((p) => p[1]);
  const lo = Math.min(...b) - 3, hi = Math.max(...b) + 3;
  const line = pts.map((p) => [((p[0] - t0) / Math.max(1, t1 - t0)) * 100, 22 - ((p[1] - lo) / (hi - lo)) * 20].map((v) => v.toFixed(2)).join(",")).join(" ");
  const pl = document.createElementNS("http://www.w3.org/2000/svg", "polyline"); pl.setAttribute("points", line);
  svg.appendChild(pl);
  return svg;
}

// The last 7 days of distance, one bar per day of THIS screen's calendar, from the stored summaries.
function weekBars(days) {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const sums = Array(7).fill(0);
  for (const [at, m] of days || []) {
    const d = new Date(at); d.setHours(0, 0, 0, 0);
    const i = 6 - Math.round((today - d) / 86_400_000);
    if (i >= 0 && i < 7) sums[i] += m;
  }
  const total = sums.reduce((a, b) => a + b, 0);
  if (!total) return null;
  const box = txt("div");
  box.appendChild(txt("h4", null, tt("week", { km: km(total, 1) }, "Last 7 days · {km}")));
  const bars = txt("div", "ac-week");
  const top = Math.max(...sums), wd = (dt) => { try { return new Intl.DateTimeFormat(_lang || undefined, { weekday: "narrow" }).format(dt); } catch (_) { return ""; } };
  sums.forEach((m, i) => {
    const day = txt("div", "ac-day"), dt = new Date(today.getTime() - (6 - i) * 86_400_000);
    const bar = txt("i", m ? null : "ac-nil"); bar.style.height = m ? Math.max(6, Math.round(m / top * 100)) + "%" : "2px";
    day.title = wd(dt) + " · " + km(m, 1);
    day.appendChild(bar); day.appendChild(txt("span", null, wd(dt)));
    bars.appendChild(day);
  });
  box.appendChild(bars);
  return box;
}

// One stored activity, opened from its row: everything its summary kept.
function detail(h) {
  const g = txt("div", "ac-detail");
  g.appendChild(fig(clock(h.elapsed_s || 0), tt("time", null, "Time")));
  g.appendChild(fig(typeof h.distance_m === "number" ? km(h.distance_m, 2) : dash, tt("distance", null, "Distance")));
  g.appendChild(fig(h.avg_speed_kmh != null ? num(h.avg_speed_kmh, 1) + " km/h" : dash, tt("avg_speed", null, "Avg speed")));
  g.appendChild(fig(h.hr_avg ? String(h.hr_avg) : dash, tt("hr_avg", null, "Avg heart rate")));
  g.appendChild(fig(h.hr_max ? String(h.hr_max) : dash, tt("hr_max", null, "Max heart rate")));
  g.appendChild(fig(h.climb_m != null ? h.climb_m + " m" : dash, tt("climb", null, "Climb")));
  return g;
}

export function render(el, data, ctx) {
  _T = (ctx && typeof ctx.t === "function") ? ctx.t : null;
  _lang = (ctx && ctx.lang) || undefined;
  S.ctx = ctx;
  injectStyles();
  el.className = "hb-activity";
  el.textContent = "";
  clearInterval(el._acTick);
  const d = data || {};
  const repaint = () => { if (el.isConnected) render(el, d, ctx); };

  if (d.status !== "running") {
    S.want = null;                                    // a session still starting for an ended activity stops itself
    S.drawn = null; S.repaint = null;                 // … and its late answer never repaints the ended running face
    if (S.session) stopSensors();
    el.appendChild(txt("div", "ac-note", tt("start_hint", null, "Start an activity — or just say «I'm starting my ride».")));
    const kinds = txt("div", "ac-kinds");
    for (const k of ["cycling", "running", "walking", "driving"]) {
      const b = txt("button", "ac-btn", kindLabel(k));
      b.onclick = () => { S.tapped = true; b.disabled = true; ctx.action("start", { kind: k }); };
      kinds.appendChild(b);
    }
    el.appendChild(kinds);
    el.appendChild(sensorsNote(ctx));
    el.appendChild(strapRow(ctx, repaint));
    const week = weekBars(d.days);
    if (week) el.appendChild(week);
    const hist = d.history || [];
    if (hist.length) {
      el.appendChild(txt("h4", null, tt("recent", null, "Recent")));
      const list = txt("div", "ac-hist");
      for (const h of hist) {
        const row = txt("button", "ac-row");
        row.setAttribute("aria-expanded", String(S.open === h.started_at));
        row.appendChild(txt("b", null, (h.label || kindLabel(h.kind)) + " · " + new Date(h.started_at).toLocaleDateString(_lang)));
        row.appendChild(txt("span", null, (typeof h.distance_m === "number" ? km(h.distance_m, 1) : dash) + " · " + clock(h.elapsed_s || 0) + (h.hr_avg ? " · ♥ " + h.hr_avg : "")));
        row.onclick = () => { S.open = S.open === h.started_at ? null : h.started_at; repaint(); };
        list.appendChild(row);
        if (S.open === h.started_at) list.appendChild(detail(h));
      }
      el.appendChild(list);
    }
    reportShown(ctx, d);
    return;
  }

  S.repaint = () => { if (el.isConnected && S.drawn === d) render(el, d, ctx); };
  S.drawn = d;
  if (S.failedFor && S.failedFor !== (d.started_at || 0)) { S.failedFor = null; S.error = null; }   // a new activity: try again
  if (S.session && S.sessionFor !== (d.started_at || 0)) stopSensors().then(() => ensureSensors(d, ctx));   // ended + restarted elsewhere
  else ensureSensors(d, ctx);
  const hr = txt("div", "ac-hr");
  hr.appendChild(txt("b", null, d.heart_rate != null ? String(d.heart_rate) : dash));
  hr.appendChild(txt("span", null, d.heart_rate != null ? tt("bpm", null, "bpm")
    : d.has_heart_rate ? tt("hr_waiting", null, "strap not sending") : tt("hr_none", null, "no heart-rate strap")));
  el.appendChild(hr);
  const spark = sparkSvg(d.hr_recent);
  if (spark) el.appendChild(spark);
  const grid = txt("div", "ac-grid");
  const timeFig = fig(clock(d.elapsed_s || 0), tt("time", null, "Time"));
  grid.appendChild(timeFig);
  grid.appendChild(fig(d.has_location ? km(d.distance_m || 0, 2) : dash, tt("distance", null, "Distance")));
  grid.appendChild(fig(d.speed_kmh != null ? num(d.speed_kmh, 1) + " km/h" : dash, tt("speed", null, "Speed")));
  grid.appendChild(fig(d.climb_m != null ? d.climb_m + " m" : dash, tt("climb", null, "Climb")));
  el.appendChild(grid);
  el.appendChild(routeSvg(d.route || []));
  // «recording here» only with a live sensor session: a claim with no session reads nothing (V2-884 step-5 audit P2-2)
  const here = ownsIt(d);
  const where = here
    ? (S.session.background ? tt("here_locked", null, "Recording on this phone — it keeps going with the screen locked.")
      : tt("here", null, "Recording on this screen — keep it open."))
    : d.owner && d.owner !== S.owner ? tt("elsewhere", null, "Recording on your other screen.")
      : S.error ? tt("no_sensors", { why: whyLabel(S.error) }, "This screen cannot read the sensors ({why}).")
        : tt("waiting", null, "Waiting for the screen that records it.");
  el.appendChild(txt("div", "ac-note", where));
  if (here && !d.has_location && (d.elapsed_s || 0) >= 20) el.appendChild(txt("div", "ac-note", tt("gps_waiting", null, "No GPS fix yet — distance starts when it arrives.")));
  const stop = txt("button", "ac-btn ac-stop", tt("stop", { kind: kindLabel(d.kind) }, "End {kind}"));
  stop.onclick = async () => { stop.disabled = true; await stopSensors(); ctx.action("stop", {}); };
  el.appendChild(stop);
  const t0 = (d.started_at || Date.now());
  el._acTick = setInterval(() => {
    if (!el.isConnected) { clearInterval(el._acTick); return; }
    timeFig.firstChild.textContent = clock(Math.max(0, Math.floor((Date.now() - t0) / 1000)));
  }, 1000);
  reportShown(ctx, d);
}

// This screen records it: a live session for THIS activity, claimed — by the stored owner, or by the claim's own «ok»
// when the push carrying it has not arrived yet.
function ownsIt(d) {
  return !!(S.session && S.sessionFor === (d.started_at || 0) && (d.owner === S.owner || !d.owner));
}

// V2-884 — what the card SHOWS, said through the host's one door after every paint with the revision it applied:
// whether an activity runs, which, and WHERE it is recorded as the card paints it: here (a live sensor session on this
// screen), elsewhere (another screen claimed it), none (nobody reads the sensors yet, or this screen cannot).
function reportShown(ctx, d) {
  if (!ctx || typeof ctx.state !== "function") return;
  const on = d.status === "running", kind = ["cycling", "running", "walking", "driving"].includes(d.kind) ? d.kind : "";
  const recorder = !on ? "none" : ownsIt(d) ? "here" : d.owner && d.owner !== S.owner ? "elsewhere" : "none";
  try { Promise.resolve(ctx.state({ phase: on ? "running" : "idle", kind: on && kind ? kind : "none", recorder },
    { applied: true, of: d })).catch(() => {}); } catch (_) {}
}
