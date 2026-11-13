// Cycling — shared helpers of the card: the translation helper, DOM builders, number and date formats.

let _T = null;
let _lang = "en";
export function setT(ctx) {
  _T = (ctx && typeof ctx.t === "function") ? ctx.t : null;
  try { _lang = (ctx && ctx.lang) || "en"; } catch (_) { _lang = "en"; }
}
export function lang() { return _lang; }

export function tt(key, params, fb) {
  try { if (_T) { const s = _T("widgets.cycling." + key, params); if (s && s !== "widgets.cycling." + key) return s; } } catch (_) {}
  let s = fb;
  if (params) for (const k in params) s = s.split("{" + k + "}").join(String(params[k]));
  return s;
}

export function txt(tag, cls, s) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (s != null) e.textContent = s;
  return e;
}

export function btn(cls, label, onclick, title) {
  const b = txt("button", cls, label);
  b.type = "button";
  if (title) { b.title = title; b.setAttribute("aria-label", title); }
  if (onclick) b.onclick = onclick;
  return b;
}

// A destructive button that asks once in place: the first tap turns it into «Sure?», the second does it.
export function confirmBtn(cls, label, onConfirm, title) {
  const b = btn(cls, label, null, title);
  let armed = false, timer = null;
  b.onclick = (e) => {
    if (e && e.stopPropagation) e.stopPropagation();
    if (!armed) {
      armed = true; b.textContent = tt("sure", null, "Sure?"); b.classList.add("is-armed");
      timer = setTimeout(() => { armed = false; b.textContent = label; b.classList.remove("is-armed"); }, 4000);
      return;
    }
    clearTimeout(timer); onConfirm();
  };
  return b;
}

export const dash = "–";

export function fmtSec(sec) {
  const s0 = Math.max(0, Math.round(Number(sec) || 0));
  const h = Math.floor(s0 / 3600), m = Math.floor((s0 % 3600) / 60), s = s0 % 60;
  return (h ? h + ":" + String(m).padStart(2, "0") : String(m)) + ":" + String(s).padStart(2, "0");
}
export function fmtKm(km) { return (Math.round((Number(km) || 0) * 100) / 100).toFixed(2); }
export function fmtDelta(sec) {           // a segment delta: under a minute «32s», else «1:03»
  const r = Math.round(Math.abs(Number(sec) || 0));
  if (r < 60) return r + "s";
  return Math.floor(r / 60) + ":" + String(r % 60).padStart(2, "0");
}
export function avgKmh(distM, timeSec) {  // over the segment's CANONICAL distance: a better time is a better mean
  if (!distM || !timeSec) return dash;
  return ((distM / 1000) / (timeSec / 3600)).toFixed(1);
}
export function date(iso, opts) {
  try { return new Intl.DateTimeFormat(_lang, opts).format(new Date(iso)); } catch (_) { return String(iso || "").slice(0, 10); }
}
export function rideTitle(r) {
  return (r && r.name) || date(r && r.started_at, { weekday: "short", day: "numeric", month: "short" });
}

// Breadcrumbs: where «back» goes is always said.
export function crumbs(items) {
  const nav = txt("nav", "hb-crumbs cy-crumbs");
  items.forEach((it, i) => {
    if (i) nav.appendChild(txt("span", "hb-crumb-sep", "›"));
    if (it.go) { const b = btn("hb-crumb", it.label, it.go); nav.appendChild(b); }
    else nav.appendChild(txt("span", "hb-crumb-cur", it.label));
  });
  return nav;
}

export function stat(value, label, cls) {
  const c = txt("div", "cy-stat" + (cls ? " " + cls : ""));
  c.appendChild(txt("div", "cy-stat-lbl", label));
  c.appendChild(txt("div", "cy-stat-val", value));
  return c;
}

// A light: a level (green/yellow/red/gray) said by colour AND by shape, never by colour alone.
export function light(level) {
  const shape = { green: "●", yellow: "▲", red: "■", gray: "○" }[level] || "○";
  return txt("span", "cy-light cy-light-" + (level || "gray"), shape);
}

// A small line chart (heart rate, elevation) as an SVG: [[x, y], …].
export function sparkline(points, cls) {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("class", "cy-spark " + (cls || ""));
  svg.setAttribute("viewBox", "0 0 100 30");
  svg.setAttribute("preserveAspectRatio", "none");
  if (!points || points.length < 2) return svg;
  const xs = points.map((p) => p[0]), ys = points.map((p) => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const sx = (x) => ((x - x0) / Math.max(1e-9, x1 - x0)) * 100, sy = (y) => 28 - ((y - y0) / Math.max(1e-9, y1 - y0)) * 26;
  const pl = document.createElementNS(NS, "polyline");
  pl.setAttribute("points", points.map((p) => sx(p[0]).toFixed(2) + "," + sy(p[1]).toFixed(2)).join(" "));
  pl.setAttribute("vector-effect", "non-scaling-stroke");
  svg.appendChild(pl);
  return svg;
}
