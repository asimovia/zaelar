// classics-kit.js — the drawing helpers the 17 classic faces share, and the late-bound lookup one classic uses to
// draw another (the 8-bit pixel face resamples the bubble). V2-928.
import { fib, HEAD } from "./rig.js?v=1";

export const C = {
  blue: "#4f8cff", violet: "#b366ff", iris: "#b07cff", amber: "#ffb14a", core: "#ffe2a3", orange: "#f08a24",
  cyan: "#38d9ff", pink: "#ff5fd2", white: "#eef3ff", navy: "#0b1226",
};
export const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
export const TAU = Math.PI * 2;

// ---------------------------------------------------------------- helpers
export function path(ctx, pts, close) {
  ctx.beginPath();
  pts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
  if (close) ctx.closePath();
}
export const proj = (G, uvs, lift) => uvs.map((uv) => G.P(uv, lift));
export function mouthOf(G, lift) {
  const m = G.mouth();
  const up = proj(G, m.upper, lift), lo = proj(G, m.lower, lift);
  return { m, up, lo, all: up.concat(lo.slice().reverse()) };
}
export function circle(ctx, x, y, r) { ctx.beginPath(); ctx.arc(x, y, Math.max(0.1, r), 0, TAU); }
export function head(G) {
  const c = G.proj(0, 0, 0);
  return { x: c.x, y: c.y, rx: HEAD.x * c.s, ry: HEAD.y * c.s, rot: G.r.roll };
}
export function ellipse(ctx, h, k = 1) { ctx.beginPath(); ctx.ellipse(h.x, h.y, h.rx * k, h.ry * k, h.rot, 0, TAU); }
export function lin(ctx, x0, y0, x1, y1, stops) {
  const g = ctx.createLinearGradient(x0, y0, x1, y1);
  stops.forEach((c, i) => g.addColorStop(i / (stops.length - 1), c));
  return g;
}
export function rad(ctx, x, y, r0, r1, stops) {
  const g = ctx.createRadialGradient(x, y, r0, x, y, r1);
  stops.forEach((c, i) => g.addColorStop(i / (stops.length - 1), c));
  return g;
}
// points every `step` px along a projected polyline
export function along(pts, step) {
  const out = [];
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1], b = pts[i], d = Math.hypot(b.x - a.x, b.y - a.y);
    const n = Math.max(1, Math.floor(d / step));
    for (let k = 0; k < n; k++) out.push({ x: a.x + ((b.x - a.x) * k) / n, y: a.y + ((b.y - a.y) * k) / n });
  }
  return out;
}
export function segDist(px, py, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay, l = dx * dx + dy * dy || 1;
  const t = clamp(((px - ax) * dx + (py - ay) * dy) / l);
  return Math.hypot(px - ax - t * dx, py - ay - t * dy);
}
export function polyDist(px, py, pts) {
  let d = 1e9;
  for (let i = 1; i < pts.length; i++) d = Math.min(d, segDist(px, py, pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1]));
  return d;
}
export function inPoly(px, py, pts) {
  let c = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const [xi, yi] = pts[i], [xj, yj] = pts[j];
    if ((yi > py) !== (yj > py) && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) c = !c;
  }
  return c;
}
// the Zaelar logo eye: almond outline (blue→violet), violet iris ring, amber core
export function logoEye(ctx, G, e, k = 1, opts = {}) {
  const ol = proj(G, e.outline), ic = G.P(e.iris), s = ic.s;
  const x0 = Math.min(...ol.map((p) => p.x)), x1 = Math.max(...ol.map((p) => p.x));
  ctx.save();
  if (opts.fill) { path(ctx, ol, true); ctx.fillStyle = opts.fill; ctx.fill(); }
  path(ctx, ol, true); ctx.clip();
  circle(ctx, ic.x, ic.y, e.irisR * s);
  ctx.lineWidth = Math.max(1, 0.022 * s * k); ctx.strokeStyle = opts.iris || C.iris; ctx.stroke();
  circle(ctx, ic.x, ic.y, e.coreR * s);
  ctx.fillStyle = rad(ctx, ic.x - e.coreR * s * 0.3, ic.y - e.coreR * s * 0.3, 0, e.coreR * s, [C.core, C.amber, C.orange]);
  ctx.fill();
  ctx.restore();
  path(ctx, ol, true);
  ctx.lineWidth = Math.max(1, 0.02 * s * k); ctx.strokeStyle = opts.stroke || lin(ctx, x0, 0, x1, 0, [C.blue, C.violet]);
  ctx.stroke();
}
export function glowOn(ctx, color, blur) { ctx.shadowColor = color; ctx.shadowBlur = blur; }
export function glowOff(ctx) { ctx.shadowBlur = 0; }
// glyph sprites (for the binary style)
const _spr = new Map();
export function glyph(ch, color) {
  const key = ch + color;
  if (_spr.has(key)) return _spr.get(key);
  const c = document.createElement("canvas"); c.width = c.height = 32;
  const x = c.getContext("2d");
  x.fillStyle = color; x.font = "bold 26px ui-monospace, Menlo, monospace"; x.textAlign = "center"; x.textBaseline = "middle";
  if (ch === "•") { x.beginPath(); x.arc(16, 16, 9, 0, TAU); x.fill(); } else x.fillText(ch, 16, 17);
  _spr.set(key, c);
  return c;
}
// A plain, solid face drawn small: the source the pixel and ASCII styles resample.
export function flatFace(ctx, G, pal) {
  const h = head(G);
  ellipse(ctx, h); ctx.fillStyle = pal.head; ctx.fill();
  ellipse(ctx, { ...h, x: h.x + h.rx * 0.25, y: h.y + h.ry * 0.2 }, 0.8); ctx.fillStyle = pal.shade; ctx.fill();
  ellipse(ctx, { ...h, x: h.x - h.rx * 0.2, y: h.y - h.ry * 0.25 }, 0.55); ctx.fillStyle = pal.light; ctx.fill();
  for (const side of [-1, 1]) {
    const e = G.eye(side), ol = proj(G, e.outline), ic = G.P(e.iris);
    path(ctx, ol, true); ctx.fillStyle = pal.eye; ctx.fill();
    ctx.save(); path(ctx, ol, true); ctx.clip();
    circle(ctx, ic.x, ic.y, e.irisR * ic.s); ctx.fillStyle = pal.iris; ctx.fill();
    circle(ctx, ic.x, ic.y, e.coreR * ic.s); ctx.fillStyle = pal.core; ctx.fill();
    ctx.restore();
    path(ctx, proj(G, G.brow(side)), false); ctx.lineWidth = Math.max(1, 0.05 * ic.s); ctx.strokeStyle = pal.line; ctx.stroke();
  }
  const mo = mouthOf(G);
  path(ctx, mo.all, true); ctx.fillStyle = pal.mouth; ctx.fill();
  ctx.lineWidth = Math.max(1, 0.04 * mo.up[0].s); ctx.strokeStyle = pal.line; ctx.stroke();
}

// ---------------------------------------------------------------- the styles

/** Every classic, filled by classics.js; read lazily so a style may draw another. */
export const ALL = [];
export const byId = (id) => ALL.find((x) => x.id === id);
