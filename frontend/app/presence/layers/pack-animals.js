// layers/pack-animals.js — a LAYER PACK: new ears, mouths, face markings and accessories on top of the one base.
// Nothing here touches the base or the pipeline: each piece is `addLayer(slot, type, { draw, tall })`.
import { addLayer, kit } from "../creator.js?v=1";

const { mix, rgba, poly, circle, oval } = kit;
const wiggle = (r, k = 1) => (Math.sin(r.t * 2.2) * 0.04 + r.energy * 0.05 * Math.sin(r.t * 9)) * k;
const dims = (spec) => ({ hx: spec.head.w, hy: 1.15 * spec.head.h });
const earCol = (spec) => spec.ears.color || spec.head.skin;
const outline = (ctx, G, spec) => { if (spec.head.outline > 0) { ctx.lineWidth = spec.head.outline * G.R; ctx.strokeStyle = spec.head.outlineColor; ctx.stroke(); } };

// ------------------------------------------------------------------ ears
// fennec: huge, wide, rounded triangles
addLayer("ears", "fennec", { tall: true, draw(ctx, G, spec, front) {
  if (front) return;
  const { hx, hy } = dims(spec), w = wiggle(G.r), P = (u, v) => G.proj(u, v, -0.15);
  for (const side of [-1, 1]) {
    const shape = (k) => {
      const a = P(side * hx * (0.18 + 0.1 * (1 - k)), hy * (0.78 + 0.05 * (1 - k))), b = P(side * hx * (0.62 + 0.62 * k + w), hy * (0.95 + 0.72 * k)),
        c = P(side * hx * (0.98 - 0.08 * (1 - k)), hy * (0.28 + 0.1 * (1 - k)));
      const qa = P(side * hx * (0.3 + 0.2 * k), hy * (1.0 + 0.62 * k)), qb = P(side * hx * (0.98 + 0.42 * k), hy * (0.62 + 0.5 * k));
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.quadraticCurveTo(qa.x, qa.y, b.x, b.y); ctx.quadraticCurveTo(qb.x, qb.y, c.x, c.y); ctx.closePath();
    };
    shape(1); ctx.fillStyle = earCol(spec); ctx.fill(); outline(ctx, G, spec);
    shape(0.82); ctx.fillStyle = spec.ears.inner; ctx.fill();
  }
} });
// monkey: big round ears on the sides
addLayer("ears", "monkey", { draw(ctx, G, spec, front) {
  if (front) return;
  const { hx, hy } = dims(spec);
  for (const side of [-1, 1]) {
    const c = G.proj(side * hx * 1.0, hy * 0.08, -0.1);
    circle(ctx, c.x, c.y, 0.27 * c.s); ctx.fillStyle = earCol(spec); ctx.fill(); outline(ctx, G, spec);
    circle(ctx, c.x + side * 0.02 * c.s, c.y, 0.16 * c.s); ctx.fillStyle = spec.ears.inner; ctx.fill();
  }
} });
// floppy: long ears hanging in front (puppies, lop bunnies), they swing with the voice
addLayer("ears", "floppy", { draw(ctx, G, spec, front) {
  if (!front) return;
  const { hx, hy } = dims(spec), w = wiggle(G.r, 1.6);
  for (const side of [-1, 1]) {
    const a = G.proj(side * hx * 0.66, hy * 0.74, 0.12), b = G.proj(side * hx * (1.06 + w), -hy * 0.32, 0.08);
    const ang = Math.atan2(b.y - a.y, b.x - a.x) + Math.PI / 2, len = Math.hypot(b.x - a.x, b.y - a.y);
    oval(ctx, (a.x + b.x) / 2, (a.y + b.y) / 2, 0.2 * a.s, len / 2 + 0.06 * a.s, ang);
    ctx.fillStyle = earCol(spec); ctx.fill(); outline(ctx, G, spec);
    oval(ctx, (a.x + b.x) / 2 + side * 0.02 * a.s, (a.y + b.y) / 2 + 0.03 * a.s, 0.1 * a.s, len / 2.6, ang);
    ctx.fillStyle = rgba(spec.ears.inner, 0.5); ctx.fill();
  }
} });

// ------------------------------------------------------------------ mouths
// duck bill: a wide rounded upper bill; the lower one drops with the voice
addLayer("mouth", "bill", { draw(ctx, G, spec) {
  const r = G.r, m = G.mouth(), c = G.P([0, m.my + 0.07], 0.09), s = c.s * spec.mouth.size, col = spec.mouth.color;
  const W = 0.3 * s, Hu = 0.11 * s, drop = r.open * 0.13 * s, tilt = r.roll;
  oval(ctx, c.x, c.y + Hu * 0.45 + drop, W * 0.82, Hu * 0.65, tilt); ctx.fillStyle = mix(col, "#000000", 0.18); ctx.fill();
  if (r.open > 0.08) { oval(ctx, c.x, c.y + Hu * 0.45 + drop * 0.5, W * 0.62, drop * 0.55 + 0.01 * s, tilt); ctx.fillStyle = mix(col, "#3a0d0d", 0.75); ctx.fill(); }
  oval(ctx, c.x, c.y, W, Hu, tilt); ctx.fillStyle = col; ctx.fill();
  oval(ctx, c.x - W * 0.25, c.y - Hu * 0.35, W * 0.35, Hu * 0.25, tilt); ctx.fillStyle = "rgba(255,255,255,.28)"; ctx.fill();
  for (const side of [-1, 1]) { oval(ctx, c.x + side * W * 0.22, c.y - Hu * 0.2, 0.012 * s, 0.02 * s); ctx.fillStyle = mix(col, "#000000", 0.45); ctx.fill(); }
  // smile corners
  ctx.beginPath(); ctx.moveTo(c.x - W * 0.95, c.y + Hu * 0.1); ctx.quadraticCurveTo(c.x, c.y + Hu * (0.9 + r.smile * 0.6), c.x + W * 0.95, c.y + Hu * 0.1);
  ctx.lineWidth = Math.max(1, 0.012 * s); ctx.strokeStyle = mix(col, "#000000", 0.35); ctx.stroke();
} });

// ------------------------------------------------------------------ face markings
// lemur: white face with big dark eye patches
addLayer("muzzle", "lemur", { draw(ctx, G, spec) {
  kit.builtin.muzzle(ctx, G, { ...spec, muzzle: { type: "face", color: spec.muzzle.color } });
  kit.builtin.muzzle(ctx, G, { ...spec, muzzle: { type: "panda", color: "#24242c" } });
} });

// ------------------------------------------------------------------ accessories
// dragon spikes along the top of the head
addLayer("extra", "spikes", { tall: true, draw(ctx, G, spec, front) {
  if (front) return;
  const { hx, hy } = dims(spec), col = spec.extra.color;
  for (let k = -2; k <= 2; k++) {
    const u = k * 0.17 * hx, top = hy * 0.94 * Math.sqrt(Math.max(0, 1 - (u / hx) ** 2));
    const h = (0.32 - Math.abs(k) * 0.06) * hy, sway = Math.sin(G.r.t * 2 + k) * 0.015;
    const a = G.proj(u - 0.08, top - 0.04, -0.05), b = G.proj(u + 0.08, top - 0.04, -0.05), t = G.proj(u + sway, top + h, -0.05);
    poly(ctx, [a, t, b]); ctx.fillStyle = col; ctx.fill();
    poly(ctx, [a, t, b]); ctx.lineWidth = 1; ctx.strokeStyle = mix(col, "#000000", 0.3); ctx.stroke();
  }
} });
// round glasses
addLayer("extra", "glasses", { draw(ctx, G, spec, front) {
  if (!front) return;
  const col = spec.extra.color, L = G.eye(-1), R = G.eye(1);
  const pl = G.P(L.c, 0.08), pr = G.P(R.c, 0.08), s = pl.s, rr = Math.max(L.w * 0.95, 0.17 * L.k) * s;
  for (const p of [pl, pr]) { circle(ctx, p.x, p.y, rr); ctx.fillStyle = "rgba(255,255,255,.1)"; ctx.fill(); ctx.lineWidth = Math.max(2, 0.03 * s); ctx.strokeStyle = col; ctx.stroke(); }
  ctx.beginPath(); ctx.moveTo(pl.x + rr, pl.y); ctx.quadraticCurveTo((pl.x + pr.x) / 2, pl.y - rr * 0.35, pr.x - rr, pr.y); ctx.stroke();
  for (const [p, side] of [[pl, -1], [pr, 1]]) { const e = G.pt(side * spec.head.w * 0.97, (side < 0 ? L : R).c[1] + 0.03, 0); ctx.beginPath(); ctx.moveTo(p.x + side * rr, p.y); ctx.lineTo(e.x, e.y); ctx.stroke(); }
} });
// headphones: the band goes behind the head (shows above it), the cups in front
addLayer("extra", "headphones", { tall: true, draw(ctx, G, spec, front) {
  const { hx, hy } = dims(spec), col = spec.extra.color;
  if (!front) {
    const pts = []; for (let i = 0; i <= 24; i++) { const a = Math.PI * (i / 24); pts.push(G.proj(-Math.cos(a) * hx * 1.04, Math.sin(a) * hy * 1.1 + 0.02, -0.2)); }
    ctx.beginPath(); pts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
    ctx.lineWidth = 0.09 * pts[12].s; ctx.lineCap = "round"; ctx.strokeStyle = mix(col, "#000000", 0.25); ctx.stroke();
    return;
  }
  for (const side of [-1, 1]) {
    const c = G.proj(side * hx * 1.0, 0.02, 0.05);
    oval(ctx, c.x, c.y, 0.17 * c.s, 0.27 * c.s, G.r.roll); ctx.fillStyle = col; ctx.fill();
    oval(ctx, c.x - side * 0.03 * c.s, c.y, 0.09 * c.s, 0.18 * c.s, G.r.roll); ctx.fillStyle = mix(col, "#000000", 0.4); ctx.fill();
    ctx.save(); ctx.shadowColor = col; ctx.shadowBlur = 10 * (0.3 + G.r.energy);
    circle(ctx, c.x + side * 0.05 * c.s, c.y - 0.12 * c.s, 0.025 * c.s); ctx.fillStyle = "#ffffff"; ctx.fill(); ctx.restore();
  }
} });
// white ear tufts (marmoset / tití)
addLayer("extra", "tufts", { draw(ctx, G, spec, front) {
  if (front) return;
  const { hx, hy } = dims(spec), col = spec.extra.color;
  for (const side of [-1, 1]) {
    const c = G.proj(side * hx * 1.12, hy * 0.42, -0.12);
    for (let k = 0; k < 7; k++) {
      const a = (side < 0 ? Math.PI : 0) + side * (-0.9 + k * 0.28) + Math.sin(G.r.t * 2 + k) * 0.05, len = (0.42 + 0.1 * Math.sin(k * 2.1)) * c.s;
      oval(ctx, c.x + Math.cos(a) * len * 0.5, c.y - Math.sin(a) * len * 0.5, len * 0.55, 0.05 * c.s, -a); ctx.fillStyle = k % 2 ? col : mix(col, "#c9c9c9", 0.3); ctx.fill();
    }
  }
} });
