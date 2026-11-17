// parts-head.js — what sits around the head: ears, hair and extras (drawn behind AND in front). V2-928.
import { TAU, clamp, rgb, mix, rgba, lum, hash, poly, circle, oval, glyph } from "./kit.js?v=1";

export function ears(ctx, G, spec, front) {
  const type = spec.ears.type;
  if (type === "none") return;
  const hx = spec.head.w, hy = 1.15 * spec.head.h, r = G.r;
  const col = spec.ears.color || spec.head.skin, inner = spec.ears.inner;
  const P = (u, v, z = -0.15) => G.proj(u, v, z);
  const shade = (path, c, k = 0.25) => { ctx.fillStyle = c; ctx.fill(); if (spec.head.outline > 0) { ctx.lineWidth = spec.head.outline * G.R; ctx.strokeStyle = spec.head.outlineColor; ctx.stroke(); } };
  const wig = Math.sin(r.t * 2.2) * 0.04 + r.energy * 0.05 * Math.sin(r.t * 9);
  for (const side of [-1, 1]) {
    if (type === "dog") {
      if (!front) continue;
      const base = [side * hx * 0.78, hy * 0.55], tipU = side * hx * 1.12, tipV = -hy * 0.15 - wig * 0.5;
      const pts = [P(base[0], base[1], 0.1), P(side * hx * 1.18, hy * 0.35, 0.1), P(tipU, tipV, 0.1), P(side * hx * 0.88, -hy * 0.05, 0.12), P(side * hx * 0.7, hy * 0.35, 0.15)];
      ctx.beginPath(); ctx.moveTo(pts[0].x, pts[0].y);
      ctx.bezierCurveTo(pts[1].x, pts[1].y, pts[2].x, pts[2].y, pts[2].x, pts[2].y);
      ctx.bezierCurveTo(pts[3].x, pts[3].y, pts[4].x, pts[4].y, pts[0].x, pts[0].y);
      shade(null, col);
      continue;
    }
    if (front) continue;
    if (type === "human" || type === "elf") {
      const c = P(side * hx * 0.98, hy * 0.02);
      if (type === "human") { oval(ctx, c.x, c.y, 0.12 * c.s, 0.17 * c.s); shade(null, col); oval(ctx, c.x + side * 0.02 * c.s, c.y, 0.06 * c.s, 0.1 * c.s); ctx.fillStyle = rgba(inner, 0.6); ctx.fill(); }
      else { poly(ctx, [P(side * hx * 0.9, hy * 0.18), P(side * hx * 1.45, hy * 0.42 + wig), P(side * hx * 0.92, -hy * 0.12)]); shade(null, col); }
    } else if (type === "cat" || type === "fox") {
      const big = type === "fox" ? 1.3 : 1;
      const a = P(side * hx * 0.25, hy * 0.88), b = P(side * hx * (0.62 + 0.12 * big), hy * (1.25 + 0.15 * big) + wig), c = P(side * hx * 0.88, hy * 0.5);
      poly(ctx, [a, b, c]); shade(null, col);
      const ia = P(side * hx * 0.36, hy * 0.85), ib = P(side * hx * (0.6 + 0.1 * big), hy * (1.12 + 0.12 * big) + wig), ic = P(side * hx * 0.78, hy * 0.58);
      poly(ctx, [ia, ib, ic]); ctx.fillStyle = inner; ctx.fill();
    } else if (type === "bear" || type === "mouse") {
      const rr = type === "mouse" ? 0.42 : 0.27, c = P(side * hx * 0.72, hy * 0.82 + (type === "mouse" ? 0.08 : 0));
      circle(ctx, c.x, c.y, rr * c.s); shade(null, col);
      circle(ctx, c.x, c.y, rr * 0.55 * c.s); ctx.fillStyle = inner; ctx.fill();
    } else if (type === "bunny") {
      const base = P(side * hx * 0.32, hy * 0.85), tip = P(side * hx * (0.45 + wig), hy * 2.0);
      const ang = Math.atan2(tip.y - base.y, tip.x - base.x) + Math.PI / 2, len = Math.hypot(tip.x - base.x, tip.y - base.y);
      const mx = (base.x + tip.x) / 2, my = (base.y + tip.y) / 2;
      oval(ctx, mx, my, 0.17 * base.s, len / 2, ang); shade(null, col);
      oval(ctx, mx, my + len * 0.05, 0.08 * base.s, len / 2.6, ang); ctx.fillStyle = inner; ctx.fill();
    } else if (type === "fins") {
      poly(ctx, [P(side * hx * 0.9, hy * 0.3), P(side * hx * 1.5, hy * 0.75 + wig), P(side * hx * 1.35, hy * 0.1), P(side * hx * 0.95, -hy * 0.25)]);
      shade(null, col);
    }
  }
}

// ---------------------------------------------------------------------------------------------------- hair
export function hair(ctx, G, spec, front) {
  const type = spec.hair.type;
  if (type === "none") return;
  const hx = spec.head.w, hy = 1.15 * spec.head.h, col = spec.hair.color, r = G.r;
  const P = (u, v, z = 0.25) => G.proj(u, v, z);
  const fill = (c = col) => {
    ctx.fillStyle = c; ctx.fill();
    if (spec.head.outline > 0) { ctx.lineWidth = spec.head.outline * G.R; ctx.strokeStyle = spec.head.outlineColor; ctx.stroke(); }
  };
  const arcPts = (a0, a1, rx, ry, cyv = 0, z = 0.25, n = 24) => {
    const pts = [];
    for (let i = 0; i <= n; i++) { const a = a0 + ((a1 - a0) * i) / n; pts.push(P(Math.cos(a) * rx, cyv + Math.sin(a) * ry, z)); }
    return pts;
  };
  if (!front) {
    if (type === "bob" || type === "long") {
      const low = type === "long" ? -hy * 1.25 : -hy * 0.35;
      const pts = arcPts(-0.05, Math.PI + 0.05, hx * 1.14, hy * 1.12, 0, -0.2);
      pts.push(P(-hx * 1.12, low, -0.2)); pts.push(P(hx * 1.12, low, -0.2));
      poly(ctx, pts); fill(mix(col, "#000000", 0.15));
    } else if (type === "afro") {
      for (let k = 0; k < 14; k++) {
        const a = Math.PI * 0.95 * (k / 13) + Math.PI * 0.025 - 0.05, p = P(Math.cos(a) * hx * 1.12, hy * 0.15 + Math.sin(a) * hy * 1.05, -0.3);
        circle(ctx, p.x, p.y, 0.34 * p.s); fill(mix(col, "#000000", 0.1));
      }
      const c = P(0, hy * 0.35, -0.3); oval(ctx, c.x, c.y, hx * 1.2 * c.s, hy * 0.9 * c.s); fill(mix(col, "#000000", 0.1));
    } else if (type === "buns") {
      for (const side of [-1, 1]) { const p = P(side * hx * 0.72, hy * 0.92, -0.1); circle(ctx, p.x, p.y, 0.3 * p.s); fill(); }
    }
    return;
  }
  if (type === "fringe" || type === "bob" || type === "long" || type === "buns" || type === "beanie") {
    const top = arcPts(Math.PI + 0.12, -0.12, hx * 1.03, hy * 1.03, 0, 0.25).reverse();
    const edge = [];
    const n = type === "beanie" ? 2 : 7, low = type === "beanie" ? hy * 0.5 : hy * 0.42;
    for (let i = 0; i <= 28; i++) {
      const f = i / 28, u = -hx * 0.98 + f * hx * 1.96;
      const scallop = type === "beanie" ? 0 : Math.abs(Math.sin(f * Math.PI * n)) * 0.09;
      const v = low + scallop + (type === "long" ? 0.12 * Math.abs(f - 0.5) : 0) + (Math.abs(u) > hx * 0.8 ? -0.12 : 0);
      edge.push(P(u, v, G.surfZ(u, v) + 0.03));
    }
    poly(ctx, [...top, ...edge.reverse()]); fill();
    if (type === "beanie") {
      const band = []; for (let i = 0; i <= 28; i++) { const u = -hx * 1.0 + (i / 28) * hx * 2; band.push(P(u, hy * 0.5, G.surfZ(u, hy * 0.5) + 0.05)); }
      ctx.beginPath(); band.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
      ctx.lineWidth = 0.12 * G.R; ctx.strokeStyle = mix(col, "#ffffff", 0.25); ctx.stroke();
      const pom = P(0, hy * 1.18, 0.1); circle(ctx, pom.x, pom.y, 0.16 * pom.s); fill(mix(col, "#ffffff", 0.35));
    }
  } else if (type === "spiky" || type === "mohawk") {
    const n = type === "mohawk" ? 6 : 9;
    for (let k = 0; k < n; k++) {
      const f = k / (n - 1);
      const a = type === "mohawk" ? Math.PI / 2 + (f - 0.5) * 0.5 : Math.PI * (0.12 + 0.76 * f);
      const bu = Math.cos(a) * hx * 0.98, bv = Math.sin(a) * hy * 0.98;
      const len = (type === "mohawk" ? 0.5 : 0.32) * (0.8 + 0.4 * hash(k, 3)) + r.energy * 0.03;
      const tip = P(bu * (1 + len), bv * (1 + len) + (type === "mohawk" ? 0 : 0.05), 0.1);
      const w = type === "mohawk" ? 0.07 : 0.16;
      poly(ctx, [P(bu - Math.sin(a) * w, bv + Math.cos(a) * w * 0.3, 0.2), tip, P(bu + Math.sin(a) * w, bv - Math.cos(a) * w * 0.3, 0.2)]); fill();
    }
    const cap = arcPts(Math.PI * 0.1, Math.PI * 0.9, hx * 1.0, hy * 1.0, 0, 0.3);
    const cap2 = arcPts(Math.PI * 0.9, Math.PI * 0.1, hx * 0.85, hy * 0.72, 0, 0.5);
    if (type === "spiky") { poly(ctx, [...cap, ...cap2]); fill(); }
  } else if (type === "curls") {
    for (let k = 0; k < 11; k++) {
      const a = Math.PI * (0.08 + 0.84 * (k / 10)), p = P(Math.cos(a) * hx * 0.92, Math.sin(a) * hy * 0.92, 0.3);
      circle(ctx, p.x, p.y, 0.2 * p.s); fill();
      circle(ctx, p.x - 0.05 * p.s, p.y - 0.05 * p.s, 0.07 * p.s); ctx.fillStyle = rgba("#ffffff", 0.15); ctx.fill();
    }
  } else if (type === "afro") {
    // the back layer is the cloud; in front, a soft hairline
    const top = arcPts(Math.PI + 0.25, -0.25, hx * 1.0, hy * 1.0, 0, 0.3).reverse();
    const edge = []; for (let i = 0; i <= 20; i++) { const u = -hx * 0.95 + (i / 20) * hx * 1.9; edge.push(P(u, hy * 0.62 + 0.05 * Math.sin(i), 0.5)); }
    poly(ctx, [...top, ...edge.reverse()]); fill();
  } else if (type === "tuft") {
    const b = P(0, hy * 0.95, 0.3), t1 = P(0.12, hy * 1.3, 0.2), t2 = P(-0.08, hy * 1.42, 0.2);
    ctx.beginPath(); ctx.moveTo(b.x, b.y); ctx.quadraticCurveTo(t1.x, t1.y, t2.x, t2.y);
    ctx.lineWidth = 0.06 * b.s; ctx.lineCap = "round"; ctx.strokeStyle = col; ctx.stroke();
  } else if (type === "sprout") {
    const b = P(0, hy * 0.98, 0.2), t = P(Math.sin(r.t * 1.5) * 0.04, hy * 1.32, 0.2);
    ctx.beginPath(); ctx.moveTo(b.x, b.y); ctx.lineTo(t.x, t.y); ctx.lineWidth = 0.035 * b.s; ctx.strokeStyle = "#4caf50"; ctx.stroke();
    for (const side of [-1, 1]) { oval(ctx, t.x + side * 0.1 * b.s, t.y - 0.02 * b.s, 0.11 * b.s, 0.05 * b.s, side * -0.5); ctx.fillStyle = "#66d17a"; ctx.fill(); }
  }
}

// ---------------------------------------------------------------------------------------------------- extras
export function extras(ctx, G, spec, front) {
  const type = spec.extra.type, col = spec.extra.color, r = G.r;
  if (type === "none") return;
  const hx = spec.head.w, hy = 1.15 * spec.head.h;
  const P = (u, v, z = 0) => G.proj(u, v, z);
  if (!front && (type === "antenna" || type === "antennae" || type === "horns" || type === "unicorn" || type === "halo")) {
    if (type === "antenna" || type === "antennae") {
      const list = type === "antenna" ? [0] : [-0.35, 0.35];
      for (const u0 of list) {
        const sway = Math.sin(r.t * 2 + u0 * 3) * 0.06 + r.energy * 0.05 * Math.sin(r.t * 12);
        const b = P(u0 * hx, hy * 0.9), t = P(u0 * hx * 1.5 + sway, hy * 1.45);
        ctx.beginPath(); ctx.moveTo(b.x, b.y); ctx.lineTo(t.x, t.y); ctx.lineWidth = 0.025 * b.s; ctx.strokeStyle = mix(col, "#000000", 0.3); ctx.stroke();
        ctx.save(); ctx.shadowColor = col; ctx.shadowBlur = 12 * (0.4 + r.glow);
        circle(ctx, t.x, t.y, 0.07 * b.s); ctx.fillStyle = col; ctx.fill(); ctx.restore();
      }
    } else if (type === "horns" || type === "unicorn") {
      const list = type === "unicorn" ? [0] : [-0.5, 0.5];
      for (const u0 of list) {
        const b1 = P(u0 * hx - 0.1, hy * 0.82), b2 = P(u0 * hx + 0.1, hy * 0.82), t = P(u0 * hx * 1.35, hy * (type === "unicorn" ? 1.65 : 1.4));
        poly(ctx, [b1, t, b2]); ctx.fillStyle = col; ctx.fill();
        if (type === "unicorn") for (let k = 1; k < 4; k++) {
          const f = k / 4, a = { x: b1.x + (t.x - b1.x) * f, y: b1.y + (t.y - b1.y) * f }, b = { x: b2.x + (t.x - b2.x) * (f + 0.08), y: b2.y + (t.y - b2.y) * (f + 0.08) };
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.strokeStyle = rgba("#ffffff", 0.6); ctx.lineWidth = 1.5; ctx.stroke();
        }
      }
    } else if (type === "halo") {
      const c = P(0, hy * 1.25, -0.2);
      ctx.save(); ctx.shadowColor = col; ctx.shadowBlur = 16;
      oval(ctx, c.x, c.y + Math.sin(r.t * 2) * 3, hx * 0.6 * c.s, 0.12 * c.s); ctx.lineWidth = 0.05 * c.s; ctx.strokeStyle = col; ctx.stroke();
      ctx.restore();
    }
  }
  if (front && type === "bow") {
    const c = P(hx * 0.55, hy * 0.85, 0.3);
    for (const side of [-1, 1]) { poly(ctx, [c, { x: c.x + side * 0.26 * c.s, y: c.y - 0.14 * c.s }, { x: c.x + side * 0.26 * c.s, y: c.y + 0.14 * c.s }]); ctx.fillStyle = col; ctx.fill(); }
    circle(ctx, c.x, c.y, 0.07 * c.s); ctx.fillStyle = mix(col, "#000000", 0.2); ctx.fill();
  }
  if (front && type === "crown") {
    const pts = [], n = 5;
    for (let k = 0; k <= n * 2; k++) { const f = k / (n * 2), u = (-0.45 + 0.9 * f) * hx; pts.push(P(u, hy * (k % 2 ? 1.12 : 1.32), 0.1)); }
    pts.push(P(0.45 * hx, hy * 0.96, 0.2)); pts.push(P(-0.45 * hx, hy * 0.96, 0.2));
    poly(ctx, pts); ctx.fillStyle = col; ctx.fill(); ctx.strokeStyle = mix(col, "#000000", 0.3); ctx.lineWidth = 1.5; ctx.stroke();
  }
}

