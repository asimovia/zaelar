// parts-face.js — the face itself: muzzle, eyes (incl. the Zaelar logo eye), brows, nose, mouth, cheeks. V2-928.
import { TAU, clamp, rgb, mix, rgba, lum, hash, poly, circle, oval, glyph } from "./kit.js?v=1";

export function muzzle(ctx, G, spec) {
  const type = spec.muzzle.type, col = spec.muzzle.color;
  if (type === "none") return;
  const sh = G.shape, ey = sh.eye.y, ex = sh.eye.x, my = sh.mouth.y;
  if (type === "muzzle") {
    const c = G.pt(0, (my + ey) / 2 - 0.12, 0.01);
    oval(ctx, c.x, c.y, 0.42 * c.s, 0.3 * c.s, G.r.roll); ctx.fillStyle = col; ctx.fill();
  } else if (type === "owl") {
    for (const side of [-1, 1]) { const c = G.pt(side * ex, ey, 0.01); circle(ctx, c.x, c.y, (0.2 + 0.1 * sh.eye.k) * c.s); ctx.fillStyle = col; ctx.fill(); }
  } else if (type === "panda") {
    for (const side of [-1, 1]) { const c = G.pt(side * ex, ey - 0.02, 0.01); oval(ctx, c.x, c.y, 0.17 * c.s * sh.eye.k + 0.04 * c.s, 0.13 * c.s * sh.eye.k + 0.04 * c.s, side * 0.5 + G.r.roll); ctx.fillStyle = col; ctx.fill(); }
  } else if (type === "mask") {
    const pts = [];
    for (let i = 0; i <= 30; i++) { const a = (i / 30) * TAU; pts.push(G.pt(Math.cos(a) * (ex + 0.28), ey + Math.sin(a) * 0.2 - 0.02, 0.01)); }
    poly(ctx, pts); ctx.fillStyle = col; ctx.fill();
  } else if (type === "face") {
    const pts = [];
    for (let i = 0; i <= 40; i++) {
      const a = (i / 40) * TAU, c = Math.cos(a), s = Math.sin(a);
      const u = c * (ex + 0.25) * (s < 0 ? 0.85 : 1), v = (ey + my) / 2 + s * (s > 0 ? (ey - my) / 2 + 0.22 : (ey - my) / 2 + 0.15) - (s > 0 ? Math.max(0, 0.08 - Math.abs(c) * 0.3) * 1.5 : 0);
      pts.push(G.pt(u, v, 0.01));
    }
    poly(ctx, pts); ctx.fillStyle = col; ctx.fill();
  }
}

export function eyeOne(ctx, G, spec, e, side) {
  const t = spec.eyes.type, iris = spec.eyes.iris, sclera = spec.eyes.sclera, r = G.r;
  const c = G.P(e.iris, 0.03), ec = G.P(e.c, 0.03), s = ec.s, k = e.k || 1, open = e.open;
  const dark = lum(spec.head.skin) < 0.35 && t !== "alien" ? "#0b0d16" : "#141826";
  const highlight = (x, y, rr) => { circle(ctx, x, y, rr); ctx.fillStyle = "rgba(255,255,255,.9)"; ctx.fill(); };
  const closedLine = (w) => { ctx.beginPath(); ctx.moveTo(ec.x - w, ec.y); ctx.quadraticCurveTo(ec.x, ec.y + w * 0.35, ec.x + w, ec.y); ctx.lineWidth = Math.max(1.5, 0.025 * s); ctx.lineCap = "round"; ctx.strokeStyle = dark; ctx.stroke(); };
  if (t === "porcelain") {
    const w = 0.085 * s * k, hh = Math.max(0.01 * s, 0.12 * s * k * open);
    oval(ctx, c.x, c.y, w, hh, r.roll); ctx.fillStyle = "#1e2433"; ctx.fill();
    if (open > 0.3) { circle(ctx, c.x, c.y, w * 0.32); ctx.fillStyle = r.speaking ? "#ffb14a" : iris; ctx.fill(); highlight(c.x - w * 0.35, c.y - hh * 0.45, w * 0.16); }
  } else if (t === "dot") {
    const w = 0.055 * s * k; oval(ctx, c.x, c.y, w, Math.max(w * 0.15, w * open), r.roll); ctx.fillStyle = dark; ctx.fill();
  } else if (t === "button") {
    const w = 0.07 * s * k;
    if (open < 0.25) return closedLine(w);
    oval(ctx, c.x, c.y, w, w * Math.min(1, open * 1.1), r.roll); ctx.fillStyle = dark; ctx.fill(); highlight(c.x - w * 0.35, c.y - w * 0.35, w * 0.28);
  } else if (t === "round" || t === "cyclops") {
    const big = t === "cyclops" ? 2.1 : 1, w = 0.12 * s * k * big, ox = t === "cyclops" ? G.P([0, e.c[1] + 0.02], 0.03) : ec;
    if (open < 0.18) { ctx.save(); ctx.translate(ox.x - ec.x, ox.y - ec.y); closedLine(w); ctx.restore(); return; }
    ctx.save(); oval(ctx, ox.x, ox.y, w, w * Math.min(1.05, open), r.roll); ctx.fillStyle = sclera; ctx.fill();
    ctx.lineWidth = Math.max(1, 0.012 * s); ctx.strokeStyle = rgba("#000000", 0.25); ctx.stroke(); ctx.clip();
    const ix = ox.x + (c.x - ec.x) * big, iy = ox.y + (c.y - ec.y) * big;
    circle(ctx, ix, iy, w * 0.58); ctx.fillStyle = iris; ctx.fill();
    circle(ctx, ix, iy, w * 0.3); ctx.fillStyle = "#0b0d16"; ctx.fill();
    highlight(ix - w * 0.22, iy - w * 0.24, w * 0.14);
    // upper lid in skin colour, coming down with the blink
    oval(ctx, ox.x, ox.y - w * (2 - (1 - open) * 1.2), w * 1.3, w * 1.05); ctx.fillStyle = spec.head.skin; ctx.fill();
    ctx.restore();
  } else if (t === "manga") {
    const w = 0.105 * s * k, hh = 0.16 * s * k;
    if (open < 0.2) { closedLine(w * 1.1); return; }
    ctx.save(); oval(ctx, ec.x, ec.y, w, hh * open, r.roll); ctx.fillStyle = sclera; ctx.fill(); ctx.clip();
    const g = ctx.createLinearGradient(c.x, c.y - hh, c.x, c.y + hh);
    g.addColorStop(0, mix(iris, "#000000", 0.55)); g.addColorStop(1, mix(iris, "#ffffff", 0.35));
    oval(ctx, c.x, c.y + hh * 0.08, w * 0.82, hh * 0.86); ctx.fillStyle = g; ctx.fill();
    oval(ctx, c.x, c.y + hh * 0.1, w * 0.4, hh * 0.45); ctx.fillStyle = mix(iris, "#000000", 0.75); ctx.fill();
    highlight(c.x - w * 0.32, c.y - hh * 0.32, w * 0.24); highlight(c.x + w * 0.3, c.y + hh * 0.3, w * 0.1);
    ctx.restore();
    // lash line
    ctx.beginPath(); ctx.ellipse(ec.x, ec.y, w * 1.02, hh * open * 1.02, r.roll, Math.PI * 1.05, Math.PI * 1.95);
    ctx.lineWidth = Math.max(2, 0.035 * s * k); ctx.lineCap = "round"; ctx.strokeStyle = "#141826"; ctx.stroke();
    const tip = { x: ec.x + side * w * 1.02, y: ec.y - hh * open * 0.2 };
    ctx.beginPath(); ctx.moveTo(tip.x, tip.y); ctx.lineTo(tip.x + side * w * 0.3, tip.y - hh * 0.25); ctx.stroke();
  } else if (t === "logo" || t === "ring") {
    if (t === "logo") {
      const ol = e.outline.map((uv) => G.P(uv, 0.03));
      ctx.save(); poly(ctx, ol); ctx.fillStyle = rgba("#0a0e1e", 0.85); ctx.fill(); ctx.clip();
      circle(ctx, c.x, c.y, e.irisR * s); ctx.lineWidth = Math.max(1, 0.022 * s); ctx.strokeStyle = iris; ctx.stroke();
      circle(ctx, c.x, c.y, e.coreR * s); ctx.fillStyle = "#ffb14a"; ctx.fill(); ctx.restore();
      poly(ctx, ol); ctx.lineWidth = Math.max(1.5, 0.022 * s);
      const g = ctx.createLinearGradient(ol[12].x, 0, ol[0].x, 0); g.addColorStop(0, "#4f8cff"); g.addColorStop(1, "#b366ff");
      ctx.strokeStyle = g; ctx.stroke();
    } else {
      ctx.save(); ctx.translate(c.x, c.y); ctx.scale(1, Math.max(0.08, open));
      circle(ctx, 0, 0, 0.11 * s * k); ctx.lineWidth = Math.max(2, 0.025 * s); ctx.strokeStyle = iris; ctx.stroke();
      circle(ctx, 0, 0, 0.05 * s * k); ctx.fillStyle = "#ffb14a"; ctx.fill(); ctx.restore();
    }
  } else if (t === "alien") {
    const w = 0.2 * s * k, hh = 0.12 * s * k * open, rot = side * -0.38 + r.roll;
    oval(ctx, ec.x, ec.y, w, Math.max(0.01 * s, hh), rot); ctx.fillStyle = "#05060a"; ctx.fill();
    if (open > 0.3) { oval(ctx, c.x - side * w * 0.25, c.y - hh * 0.3, w * 0.28, hh * 0.25, rot); ctx.fillStyle = rgba(iris, 0.55); ctx.fill(); highlight(c.x - w * 0.3, c.y - hh * 0.35, w * 0.08); }
  } else if (t === "cat") {
    const ol = e.outline.map((uv) => G.P(uv, 0.03));
    if (open < 0.2) { poly(ctx, ol); ctx.lineWidth = Math.max(1.5, 0.02 * s); ctx.strokeStyle = dark; ctx.stroke(); return; }
    ctx.save(); poly(ctx, ol);
    const g = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, e.w * s);
    g.addColorStop(0, mix(iris, "#ffffff", 0.4)); g.addColorStop(1, mix(iris, "#000000", 0.25));
    ctx.fillStyle = g; ctx.fill(); ctx.clip();
    oval(ctx, c.x, c.y, 0.022 * s * k * r.eyeScale, 0.11 * s * k, r.roll); ctx.fillStyle = "#06070c"; ctx.fill();
    highlight(c.x - 0.04 * s * k, c.y - 0.035 * s * k, 0.016 * s * k);
    ctx.restore(); poly(ctx, ol); ctx.lineWidth = Math.max(1.5, 0.018 * s); ctx.strokeStyle = "#141826"; ctx.stroke();
  } else if (t === "happy" || (t === "sleepy")) {
    const w = 0.1 * s * k;
    ctx.beginPath();
    if (t === "happy") { ctx.moveTo(ec.x - w, ec.y + w * 0.3); ctx.quadraticCurveTo(ec.x, ec.y - w * 0.9, ec.x + w, ec.y + w * 0.3); }
    else { ctx.moveTo(ec.x - w, ec.y - w * 0.1); ctx.quadraticCurveTo(ec.x, ec.y + w * 0.6, ec.x + w, ec.y - w * 0.1); }
    ctx.lineWidth = Math.max(2, 0.035 * s * k); ctx.lineCap = "round"; ctx.strokeStyle = dark; ctx.stroke();
  } else if (t === "led") {
    const w = 0.1 * s * k, hh = Math.max(0.02 * s, 0.17 * s * k * open);
    ctx.save(); ctx.shadowColor = iris; ctx.shadowBlur = 14 * (0.4 + r.glow);
    ctx.beginPath(); ctx.roundRect(c.x - w, c.y - hh / 2, w * 2, hh, Math.min(w, hh) * 0.35); ctx.fillStyle = iris; ctx.fill(); ctx.restore();
  }
  if (spec.eyes.lashes && (t === "round" || t === "porcelain" || t === "dot" || t === "button") && open > 0.3) {
    ctx.lineWidth = Math.max(1.5, 0.02 * s); ctx.strokeStyle = "#141826"; ctx.lineCap = "round";
    const w = (t === "round" ? 0.12 : 0.08) * s * k;
    for (let q = 0; q < 3; q++) {
      const a = -Math.PI / 2 + side * (0.35 + q * 0.35), x0 = ec.x + Math.cos(a) * w, y0 = ec.y + Math.sin(a) * w * open;
      ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x0 + Math.cos(a) * w * 0.4, y0 + Math.sin(a) * w * 0.4); ctx.stroke();
    }
  }
}
// The Zaelar logo eye, made friendly: rounder almond, glossy lens, the violet iris ring and the amber core with a
// sparkle; when it closes (blink, laugh) it becomes a happy arc in the logo's blue→violet instead of a flat line.
//   zaelar        — the logo eye, a bit rounder, glossy
//   zaelar-kawaii — big and round, two sparkles (the cutest)
//   zaelar-glow   — neon: glowing outline and core over a dark glass
//   zaelar-light  — light lens (sclera colour) for light faces: closer, less "machine"
export function zaelarEye(ctx, G, spec, e, side, variant) {
  const r = G.r, cx = e.c[0], cy = e.c[1];
  const rnd = variant === "zaelar-kawaii" ? 1.45 : variant === "zaelar-light" ? 1.3 : 1.3;
  const grow = variant === "zaelar-kawaii" ? 1.3 : variant === "zaelar-light" ? 1.12 : 1.05;
  // rounder lids for the cute variants: (1-u²)^pw instead of the logo's (1-u²)
  const pw = variant === "zaelar-kawaii" ? 0.55 : variant === "zaelar-light" ? 0.75 : 1;
  const ol = e.outline.map(([u, v]) => {
    const q = Math.max(1e-3, 1 - ((u - cx) / e.w) ** 2), f = pw === 1 ? 1 : Math.pow(q, pw - 1);
    return G.P([cx + (u - cx) * grow, cy + (v - cy) * rnd * grow * Math.min(f, 6)], 0.03);
  });
  const c = G.P(e.iris, 0.035), s = c.s;
  const x0 = Math.min(...ol.map((p) => p.x)), x1 = Math.max(...ol.map((p) => p.x));
  const grad = () => { const g = ctx.createLinearGradient(x0, 0, x1, 0); g.addColorStop(0, "#4f8cff"); g.addColorStop(1, "#b366ff"); return g; };
  const lw = Math.max(1.6, (variant === "zaelar-glow" ? 0.03 : 0.026) * s * Math.sqrt(e.k));
  if (e.open < 0.22) {                                    // closed → happy arc
    const ec = G.P(e.c, 0.03), w = (x1 - x0) / 2;
    ctx.beginPath(); ctx.moveTo(ec.x - w, ec.y + w * 0.18); ctx.quadraticCurveTo(ec.x, ec.y - w * 0.55, ec.x + w, ec.y + w * 0.18);
    ctx.lineWidth = lw * 1.25; ctx.lineCap = "round"; ctx.strokeStyle = grad(); ctx.stroke();
    return;
  }
  const lens = variant === "zaelar-light" ? spec.eyes.sclera : spec.eyes.lens || "#0a0e1e";
  const irisR = e.irisR * s * (variant === "zaelar-kawaii" ? 1.35 : 1.15), coreR = e.coreR * s * (variant === "zaelar-kawaii" ? 1.4 : 1.2);
  ctx.save();
  if (variant === "zaelar-glow") { ctx.shadowColor = "#7b6bff"; ctx.shadowBlur = 16 * (0.5 + r.glow); }
  poly(ctx, ol);
  const lg = ctx.createLinearGradient(0, Math.min(...ol.map((p) => p.y)), 0, Math.max(...ol.map((p) => p.y)));
  if (variant === "zaelar-glow") { lg.addColorStop(0, rgba(lens, 0.75)); lg.addColorStop(1, rgba(mix(lens, "#4f8cff", 0.3), 0.75)); }
  else { lg.addColorStop(0, lens); lg.addColorStop(1, mix(lens, variant === "zaelar-light" ? "#c9d4ff" : "#2a2f6a", 0.45)); }
  ctx.fillStyle = lg; ctx.fill(); ctx.restore();
  ctx.save(); poly(ctx, ol); ctx.clip();
  // iris ring
  circle(ctx, c.x, c.y, irisR); ctx.lineWidth = Math.max(1.2, 0.024 * s * Math.sqrt(e.k)); ctx.strokeStyle = spec.eyes.iris; ctx.stroke();
  if (variant === "zaelar-light") { circle(ctx, c.x, c.y, irisR * 0.98); ctx.fillStyle = rgba(spec.eyes.iris, 0.18); ctx.fill(); }
  // amber core (brighter while speaking)
  if (variant === "zaelar-glow" || r.speaking) { ctx.shadowColor = "#ffb14a"; ctx.shadowBlur = 10 * (0.4 + r.glow + r.energy); }
  const cg = ctx.createRadialGradient(c.x - coreR * 0.3, c.y - coreR * 0.3, 0, c.x, c.y, coreR);
  cg.addColorStop(0, "#ffe2a3"); cg.addColorStop(0.55, "#ffb14a"); cg.addColorStop(1, "#f08a24");
  circle(ctx, c.x, c.y, coreR * (1 + 0.12 * r.energy)); ctx.fillStyle = cg; ctx.fill(); ctx.shadowBlur = 0;
  // sparkles
  circle(ctx, c.x - irisR * 0.55, c.y - irisR * 0.55, irisR * (variant === "zaelar-kawaii" ? 0.32 : 0.24)); ctx.fillStyle = "rgba(255,255,255,.92)"; ctx.fill();
  if (variant !== "zaelar") { circle(ctx, c.x + irisR * 0.45, c.y + irisR * 0.4, irisR * 0.12); ctx.fillStyle = "rgba(255,255,255,.75)"; ctx.fill(); }
  // gloss across the top of the lens
  if (variant !== "zaelar-light") {
    const y0 = Math.min(...ol.map((p) => p.y));
    oval(ctx, (x0 + x1) / 2, y0 + (x1 - x0) * 0.12, (x1 - x0) * 0.32, (x1 - x0) * 0.07, r.roll); ctx.fillStyle = "rgba(255,255,255,.12)"; ctx.fill();
  }
  ctx.restore();
  // outline in the logo gradient
  ctx.save(); if (variant === "zaelar-glow") { ctx.shadowColor = "#b366ff"; ctx.shadowBlur = 12 * (0.5 + r.glow); }
  poly(ctx, ol); ctx.lineWidth = lw; ctx.lineJoin = "round"; ctx.strokeStyle = grad(); ctx.stroke(); ctx.restore();
  if (spec.eyes.lashes) {
    ctx.lineWidth = Math.max(1.5, 0.02 * s); ctx.strokeStyle = "#141826"; ctx.lineCap = "round";
    const top = ol.slice(1, 12), outer = side > 0 ? top.slice(0, 3) : top.slice(-3);
    for (const p of outer) { ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(p.x + side * 0.02 * s, p.y - 0.035 * s); ctx.stroke(); }
  }
}

export function eyesAll(ctx, G, spec) {
  const t = spec.eyes.type;
  if (t === "visor") {
    const a = G.pt(-G.shape.eye.x - 0.2, G.shape.eye.y, 0.04), b = G.pt(G.shape.eye.x + 0.2, G.shape.eye.y, 0.04);
    const e = G.eye(1), hh = Math.max(0.02, 0.12 * e.open) * a.s * e.k;
    ctx.save(); ctx.shadowColor = spec.eyes.iris; ctx.shadowBlur = 18 * (0.4 + G.r.glow);
    ctx.beginPath(); ctx.roundRect(a.x, (a.y + b.y) / 2 - hh / 2, b.x - a.x, hh, hh / 2); ctx.fillStyle = spec.eyes.iris; ctx.fill();
    const gx = (a.x + b.x) / 2 + G.r.gazeX * (b.x - a.x) * 0.3;
    circle(ctx, gx, (a.y + b.y) / 2, hh * 0.45); ctx.fillStyle = "#ffffff"; ctx.fill(); ctx.restore();
    return;
  }
  if (t === "cyclops") { eyeOne(ctx, G, spec, G.eye(1), 1); return; }
  for (const side of [-1, 1]) eyeOne(ctx, G, spec, G.eye(side), side);
}

export function brows(ctx, G, spec) {
  const t = spec.brows.type;
  if (t === "none") return;
  const col = spec.brows.color, sz = spec.brows.size;
  ctx.lineCap = "round"; ctx.strokeStyle = col; ctx.fillStyle = col;
  const sides = t === "unibrow" ? [0] : [-1, 1];
  for (const side of sides) {
    let pts;
    if (t === "unibrow") pts = [...G.brow(-1), ...G.brow(1)];
    else pts = G.brow(side);
    let P = pts.map((uv) => G.P(uv, 0.04));
    if (t === "arch") P = pts.map((uv, i) => G.P([uv[0], uv[1] + Math.sin((i / (pts.length - 1)) * Math.PI) * 0.035], 0.04));
    if (t === "angry") P = pts.map((uv, i) => { const k = i / (pts.length - 1), inner = side < 0 ? 1 - k : k; return G.P([uv[0], uv[1] - inner * 0.06 + 0.02], 0.04); });
    const s = P[0].s;
    if (t === "round") { const m = P[Math.floor(P.length / 2)]; oval(ctx, m.x, m.y, 0.05 * s * sz, 0.032 * s * sz, G.r.roll); ctx.fill(); continue; }
    ctx.beginPath(); P.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
    ctx.lineWidth = Math.max(1.5, (t === "thick" || t === "unibrow" ? 0.055 : 0.028) * s * sz); ctx.stroke();
  }
}

export function nose(ctx, G, spec) {
  const t = spec.nose.type, col = spec.nose.color, sz = spec.nose.size;
  if (t === "none") return;
  const sh = G.shape, v = sh.eye.y * 0.35 + sh.mouth.y * 0.65 + 0.07;
  const c = G.pt(0, v, 0.05), s = c.s * sz;
  if (t === "dot") { oval(ctx, c.x, c.y, 0.03 * s, 0.022 * s, G.r.roll); ctx.fillStyle = col; ctx.fill(); }
  else if (t === "button") { oval(ctx, c.x, c.y, 0.07 * s, 0.05 * s, G.r.roll); ctx.fillStyle = col; ctx.fill(); oval(ctx, c.x - 0.025 * s, c.y - 0.018 * s, 0.022 * s, 0.013 * s); ctx.fillStyle = "rgba(255,255,255,.5)"; ctx.fill(); }
  else if (t === "triangle" || t === "heart") {
    ctx.beginPath(); ctx.moveTo(c.x - 0.07 * s, c.y - 0.03 * s);
    if (t === "heart") { ctx.bezierCurveTo(c.x - 0.08 * s, c.y - 0.08 * s, c.x, c.y - 0.07 * s, c.x, c.y - 0.04 * s); ctx.bezierCurveTo(c.x, c.y - 0.07 * s, c.x + 0.08 * s, c.y - 0.08 * s, c.x + 0.07 * s, c.y - 0.03 * s); }
    else ctx.lineTo(c.x + 0.07 * s, c.y - 0.03 * s);
    ctx.quadraticCurveTo(c.x + 0.02 * s, c.y + 0.05 * s, c.x, c.y + 0.05 * s); ctx.quadraticCurveTo(c.x - 0.02 * s, c.y + 0.05 * s, c.x - 0.07 * s, c.y - 0.03 * s);
    ctx.fillStyle = col; ctx.fill();
    oval(ctx, c.x - 0.025 * s, c.y - 0.03 * s, 0.018 * s, 0.01 * s); ctx.fillStyle = "rgba(255,255,255,.45)"; ctx.fill();
  } else if (t === "line") {
    ctx.beginPath(); ctx.moveTo(c.x - 0.01 * s, c.y - 0.08 * s); ctx.quadraticCurveTo(c.x + 0.04 * s, c.y + 0.02 * s, c.x - 0.02 * s, c.y + 0.03 * s);
    ctx.lineWidth = Math.max(1.2, 0.015 * s); ctx.strokeStyle = col; ctx.lineCap = "round"; ctx.stroke();
  } else if (t === "snout") {
    oval(ctx, c.x, c.y - 0.01 * s, 0.13 * s, 0.09 * s, G.r.roll); ctx.fillStyle = col; ctx.fill();
    ctx.fillStyle = mix(col, "#000000", 0.45);
    for (const side of [-1, 1]) { oval(ctx, c.x + side * 0.045 * s, c.y - 0.01 * s, 0.018 * s, 0.03 * s); ctx.fill(); }
  }
}

export function mouthPart(ctx, G, spec) {
  const t = spec.mouth.type, col = spec.mouth.color, r = G.r;
  const m = G.mouth(), up = m.upper.map((uv) => G.P(uv, 0.04)), lo = m.lower.map((uv) => G.P(uv, 0.04));
  const all = up.concat(lo.slice().reverse()), s = up[0].s;
  const stroke = (w = 0.03) => { ctx.lineWidth = Math.max(1.5, w * s * Math.sqrt(spec.mouth.size)); ctx.lineJoin = ctx.lineCap = "round"; ctx.strokeStyle = col; ctx.stroke(); };
  const inner = () => {
    poly(ctx, all); ctx.fillStyle = mix(col, "#000000", 0.35); ctx.fill();
    if (r.open > 0.22) {
      ctx.save(); poly(ctx, all); ctx.clip();
      const lp = G.P([0, m.my - m.h * 0.75], 0.04);
      oval(ctx, lp.x, lp.y, m.mw * 0.55 * lp.s, m.h * 0.5 * lp.s, r.roll); ctx.fillStyle = spec.mouth.tongue; ctx.fill();
      ctx.restore();
    }
  };
  if (t === "line") { poly(ctx, all); if (r.open > 0.12) { ctx.fillStyle = rgba(mix(col, "#000000", 0.4), 0.85); ctx.fill(); } stroke(); }
  else if (t === "filled" || t === "o") { inner(); poly(ctx, all); stroke(0.025); }
  else if (t === "teeth" || t === "fangs") {
    inner();
    if (r.open > 0.08 || t === "fangs") {
      ctx.save(); poly(ctx, all); ctx.clip(); ctx.fillStyle = "#ffffff";
      if (t === "teeth") { const a = G.P([-m.mw, m.my + 0.03], 0.04), b = G.P([m.mw, m.my - Math.min(m.h * 0.3, 0.04)], 0.04); ctx.fillRect(a.x, a.y - 0.05 * s, b.x - a.x, b.y - a.y + 0.05 * s); }
      ctx.restore();
      if (t === "fangs") for (const side of [-1, 1]) { const b = G.P([side * m.mw * 0.45, m.my + 0.01], 0.05); poly(ctx, [{ x: b.x - 0.025 * s, y: b.y }, { x: b.x + 0.025 * s, y: b.y }, { x: b.x, y: b.y + 0.07 * s }]); ctx.fill(); }
    }
    poly(ctx, all); stroke(0.025);
  } else if (t === "lips") {
    inner(); poly(ctx, all); ctx.lineWidth = Math.max(3, 0.07 * s * Math.sqrt(spec.mouth.size)); ctx.lineJoin = "round"; ctx.strokeStyle = col; ctx.stroke();
    ctx.lineWidth = 1; ctx.strokeStyle = rgba("#000000", 0.25); ctx.stroke();
  } else if (t === "cat") {
    const c = G.P([0, m.my + 0.06], 0.04), w = m.mw * 0.55 * s;
    if (r.open > 0.12) { inner(); poly(ctx, all); stroke(0.022); }
    ctx.beginPath(); ctx.moveTo(c.x - w, c.y); ctx.quadraticCurveTo(c.x - w / 2, c.y + w * 0.7, c.x, c.y); ctx.quadraticCurveTo(c.x + w / 2, c.y + w * 0.7, c.x + w, c.y);
    ctx.moveTo(c.x, c.y); ctx.lineTo(c.x, c.y - w * 0.4); stroke(0.025);
  } else if (t === "beak") {
    const c = G.P([0, m.my + 0.1], 0.08), w = 0.16 * s * spec.mouth.size, gap = (0.02 + r.open * 0.2) * s;
    poly(ctx, [{ x: c.x - w, y: c.y }, { x: c.x + w, y: c.y }, { x: c.x, y: c.y + w * 0.9 }]); ctx.fillStyle = mix(col, "#000000", 0.15); ctx.fill();
    poly(ctx, [{ x: c.x - w * 0.8, y: c.y + gap * 0.3 }, { x: c.x + w * 0.8, y: c.y + gap * 0.3 }, { x: c.x, y: c.y + w * 0.6 + gap }]);
    ctx.fillStyle = mix(col, "#000000", 0.3); ctx.fill();
    poly(ctx, [{ x: c.x - w, y: c.y - 0.005 * s }, { x: c.x + w, y: c.y - 0.005 * s }, { x: c.x, y: c.y + w * 0.75 }]); ctx.fillStyle = col; ctx.fill();
  } else if (t === "led") {
    ctx.save(); ctx.shadowColor = col; ctx.shadowBlur = 12; ctx.fillStyle = col;
    for (let k = 0; k < 7; k++) {
      const x = (k - 3) * 0.055 * spec.mouth.size, amp = r.open * (0.55 + 0.45 * Math.sin(r.t * 18 + k * 1.7)) * (1 - Math.abs(k - 3) / 5);
      const hh = 0.02 + 0.24 * amp, p = G.P([x, m.my + r.smile * 0.03 * (x / 0.2) ** 2], 0.04);
      ctx.fillRect(p.x - 0.017 * s, p.y - (hh * s) / 2, 0.034 * s, hh * s);
    }
    ctx.restore();
  } else if (t === "wave") {
    const a = G.P([-m.mw - 0.05, m.my], 0.04), b = G.P([m.mw + 0.05, m.my], 0.04);
    ctx.beginPath();
    for (let i = 0; i <= 50; i++) {
      const k = i / 50, env = Math.sin(Math.PI * k), y = Math.sin(k * 26 + r.t * 14) * 0.6 + Math.sin(k * 11 - r.t * 9) * 0.4;
      const x = a.x + (b.x - a.x) * k, yy = a.y + (b.y - a.y) * k + y * (0.004 + 0.12 * r.open) * s * env - r.smile * 0.05 * s * env;
      i ? ctx.lineTo(x, yy) : ctx.moveTo(x, yy);
    }
    stroke(0.025);
  }
}

export function cheeks(ctx, G, spec) {
  const ch = spec.cheeks, sh = G.shape;
  for (const side of [-1, 1]) {
    const c = G.pt(side * (sh.eye.x + 0.12), sh.eye.y - 0.27, 0.03), s = c.s;
    if (ch.blush > 0) { oval(ctx, c.x, c.y, 0.12 * s, 0.065 * s, G.r.roll); ctx.fillStyle = `rgba(255,110,150,${ch.blush * (0.35 + 0.25 * Math.max(0, G.r.smile))})`; ctx.fill(); }
    if (ch.freckles) for (let k = 0; k < 5; k++) { circle(ctx, c.x + (hash(k, side) - 0.5) * 0.16 * s, c.y + (hash(side, k) - 0.5) * 0.08 * s, 0.009 * s); ctx.fillStyle = "rgba(120,70,40,.55)"; ctx.fill(); }
    if (ch.whiskers) {
      const b = G.pt(side * 0.22, sh.mouth.y + 0.12, 0.05);
      ctx.strokeStyle = rgba(spec.mouth.color, 0.7); ctx.lineWidth = Math.max(1, 0.01 * s); ctx.lineCap = "round";
      for (let k = -1; k <= 1; k++) { ctx.beginPath(); ctx.moveTo(b.x, b.y + k * 0.03 * s); ctx.lineTo(b.x + side * 0.32 * s, b.y + k * 0.07 * s - 0.01 * s); ctx.stroke(); }
    }
  }
}

