// Activity — a ride, a run, a walk or a drive the person starts (V2-890 F1).
// ONE screen reads the sensors (the one that claims the activity: the phone app, or the screen where he tapped
// Start); every other screen shows the same figures live from data.py. In the phone app the reading goes on with
// the screen locked (ctx.device().activity()) and the missed samples arrive in one batch when it comes back.

function injectStyles() {
  if (document.getElementById("hb-activity-css")) return;
  const s = document.createElement("style"); s.id = "hb-activity-css"; s.textContent = `
  .hb-activity{font-family:var(--sans,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif);
    width:100%;min-height:100%;box-sizing:border-box;padding:var(--sp-4,16px);display:flex;flex-direction:column;gap:14px;
    color:var(--hb-ink,#0d1622)}
  .hb-activity .ac-kinds{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
  .hb-activity .ac-btn{font-family:inherit;font-size:15px;font-weight:600;min-height:52px;border-radius:14px;cursor:pointer;
    border:1px solid var(--hb-line,#eef1f6);background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622)}
  .hb-activity .ac-btn:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-activity .ac-btn:focus-visible{outline:none;box-shadow:var(--hb-focus-ring,0 0 0 2px #AE90FF)}
  .hb-activity .ac-stop{background:var(--hb-risk,#e5484d);border-color:var(--hb-risk,#e5484d);color:var(--canvas,#101216)}
  .hb-activity .ac-hr{display:flex;align-items:baseline;justify-content:center;gap:8px}
  .hb-activity .ac-hr b{font-size:72px;font-weight:700;line-height:1;font-variant-numeric:tabular-nums;color:var(--hb-risk,#e5484d)}
  .hb-activity .ac-hr span{font-size:14px;color:var(--hb-muted,#5b6b82)}
  .hb-activity .ac-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
  .hb-activity .ac-fig{background:var(--hb-bg-soft,#f0f3f8);border-radius:12px;padding:10px 12px}
  .hb-activity .ac-fig b{display:block;font-size:26px;font-weight:600;font-variant-numeric:tabular-nums}
  .hb-activity .ac-fig span{font-size:12px;color:var(--hb-muted,#5b6b82);text-transform:uppercase;letter-spacing:.05em}
  .hb-activity .ac-note{font-size:13px;color:var(--hb-muted,#5b6b82);text-align:center}
  .hb-activity .ac-route{width:100%;height:160px;background:var(--hb-bg-soft,#f0f3f8);border-radius:12px}
  .hb-activity .ac-route polyline{fill:none;stroke:var(--hb-accent,#3D6FE0);stroke-width:3;stroke-linejoin:round;stroke-linecap:round}
  .hb-activity .ac-hist{display:flex;flex-direction:column;gap:6px}
  .hb-activity .ac-row{display:flex;justify-content:space-between;gap:8px;font-size:14px;padding:8px 0;
    border-bottom:1px solid var(--hb-line,#eef1f6)}
  .hb-activity .ac-row span{color:var(--hb-muted,#5b6b82)}
  .hb-activity h4{margin:4px 0 0;font-size:13px;font-weight:600;color:var(--hb-muted,#5b6b82);text-transform:uppercase;letter-spacing:.06em}
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

// ── The sensor session of THIS screen (module state: it outlives the re-renders every data push causes). ──
const S = { owner: "s-" + Math.random().toString(36).slice(2) + Date.now().toString(36), session: null,
  starting: false, queue: [], flush: null, tapped: false, ctx: null };

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
async function ensureSensors(d, ctx) {
  if (S.session || S.starting) return;
  if (d.owner && d.owner !== S.owner) return;
  S.starting = true;
  try {
    const dev = await ctx.device();
    const info = await dev.details();
    if (!d.owner && !S.tapped && !info.background_sessions) return;
    const c = await ctx.action("claim", { owner: S.owner });
    if (!c || !c.ok) return;
    const has = (k) => info.sensors && info.sensors[k] && info.sensors[k].available;
    const sensors = ["location", "heart_rate", "altitude", "motion_activity"].filter(has);
    const r = await dev.activity({ sensors: sensors.length ? sensors : ["location"], label: d.label || "", kind: d.kind },
      (sample) => S.queue.push(sample));
    if (r.error) { S.error = r.error; return; }
    S.session = r;
    S.flush = setInterval(flush, 5000);
  } finally { S.starting = false; S.tapped = false; }
}

async function pickStrap(ctx, box) {
  const dev = await ctx.device();
  box.textContent = tt("looking", null, "Looking for your strap… put it on and wake it.");
  const r = await dev.heartRateStraps(8);
  box.textContent = "";
  if (r.error || !r.straps.length) { box.appendChild(txt("div", "ac-note", tt("no_strap", null, "No heart-rate strap found. Check it is on, or that your watch is broadcasting heart rate."))); return; }
  for (const s of r.straps) {
    const b = txt("button", "ac-btn", s.name);
    b.onclick = async () => { await r.pick(s.id); box.textContent = ""; box.appendChild(txt("div", "ac-note", tt("strap_saved", { name: s.name }, "{name} will be used for your heart rate."))); };
    box.appendChild(b);
  }
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

export function render(el, data, ctx) {
  _T = (ctx && typeof ctx.t === "function") ? ctx.t : null;
  S.ctx = ctx;
  injectStyles();
  el.className = "hb-activity";
  el.textContent = "";
  clearInterval(el._acTick);
  const d = data || {};

  if (d.status !== "running") {
    if (S.session) stopSensors();
    el.appendChild(txt("div", "ac-note", tt("start_hint", null, "Start an activity — or just say «I'm starting my ride».")));
    const kinds = txt("div", "ac-kinds");
    for (const k of ["cycling", "running", "walking", "driving"]) {
      const b = txt("button", "ac-btn", kindLabel(k));
      b.onclick = () => { S.tapped = true; ctx.action("start", { kind: k }); };
      kinds.appendChild(b);
    }
    el.appendChild(kinds);
    const strap = txt("div", "ac-kinds");
    const sb = txt("button", "ac-btn", tt("connect_strap", null, "Heart-rate strap"));
    sb.onclick = () => pickStrap(ctx, strap);
    ctx.device().then((dev) => dev.details()).then((i) => {
      if (i && i.sensors && i.sensors.heart_rate && i.sensors.heart_rate.available) { strap.appendChild(sb); }
    }).catch(() => {});
    el.appendChild(strap);
    const hist = d.history || [];
    if (hist.length) {
      el.appendChild(txt("h4", null, tt("recent", null, "Recent")));
      const list = txt("div", "ac-hist");
      for (const h of hist) {
        const row = txt("div", "ac-row");
        row.appendChild(txt("b", null, (h.label || kindLabel(h.kind)) + " · " + new Date(h.started_at).toLocaleDateString(ctx.lang || undefined)));
        row.appendChild(txt("span", null, (h.distance_m / 1000).toFixed(1) + " km · " + clock(h.elapsed_s) + (h.hr_avg ? " · ♥ " + h.hr_avg : "")));
        list.appendChild(row);
      }
      el.appendChild(list);
    }
    reportShown(ctx, d);
    return;
  }

  ensureSensors(d, ctx);
  const hr = txt("div", "ac-hr");
  hr.appendChild(txt("b", null, d.heart_rate != null ? String(d.heart_rate) : dash));
  hr.appendChild(txt("span", null, d.heart_rate != null ? tt("bpm", null, "bpm")
    : d.has_heart_rate ? tt("hr_waiting", null, "strap not sending") : tt("hr_none", null, "no heart-rate strap")));
  el.appendChild(hr);
  const grid = txt("div", "ac-grid");
  const timeFig = fig(clock(d.elapsed_s || 0), tt("time", null, "Time"));
  grid.appendChild(timeFig);
  grid.appendChild(fig(d.has_location ? (d.distance_m / 1000).toFixed(2) + " km" : dash, tt("distance", null, "Distance")));
  grid.appendChild(fig(d.speed_kmh != null ? d.speed_kmh + " km/h" : dash, tt("speed", null, "Speed")));
  grid.appendChild(fig(d.climb_m ? d.climb_m + " m" : dash, tt("climb", null, "Climb")));
  el.appendChild(grid);
  el.appendChild(routeSvg(d.route || []));
  const where = d.owner && d.owner === S.owner
    ? (S.session && S.session.background ? tt("here_locked", null, "Recording on this phone — it keeps going with the screen locked.")
      : tt("here", null, "Recording on this screen — keep it open."))
    : d.owner ? tt("elsewhere", null, "Recording on your other screen.")
      : S.error ? tt("no_sensors", { why: S.error }, "This screen cannot read the sensors ({why}).")
        : tt("waiting", null, "Waiting for the screen that records it.");
  el.appendChild(txt("div", "ac-note", where));
  const stop = txt("button", "ac-btn ac-stop", tt("stop", { kind: kindLabel(d.kind) }, "End {kind}"));
  stop.onclick = async () => { await stopSensors(); ctx.action("stop", {}); };
  el.appendChild(stop);
  const t0 = (d.started_at || Date.now());
  el._acTick = setInterval(() => {
    if (!el.isConnected) { clearInterval(el._acTick); return; }
    timeFig.firstChild.textContent = clock(Math.max(0, Math.floor((Date.now() - t0) / 1000)));
  }, 1000);
  reportShown(ctx, d);
}

// V2-884 — what the card SHOWS, said through the host's one door after every paint with the revision it applied:
// whether an activity runs, which, and whether THIS screen is the one reading the sensors.
function reportShown(ctx, d) {
  if (!ctx || typeof ctx.state !== "function") return;
  const on = d.status === "running", kind = ["cycling", "running", "walking", "driving"].includes(d.kind) ? d.kind : "";
  const shown = { phase: on ? "running" : "idle", kind: on && kind ? kind : "none", recording: !!(on && d.owner && d.owner === S.owner) };
  try { Promise.resolve(ctx.state(shown, { applied: true })).catch(() => {}); } catch (_) {}
}
