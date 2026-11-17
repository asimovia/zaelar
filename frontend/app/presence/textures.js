// textures.js — the head's surface patterns (bits, pixels, fur, glass, stars…), drawn inside the silhouette. V2-928.
import { TAU, clamp, rgb, mix, rgba, lum, hash, poly, circle, oval, glyph } from "./kit.js?v=1";

export function texture(ctx, G, spec, sil) {
  const h = spec.head, type = h.texture, amt = h.tex, c2 = h.skin2, t = G.r.t;
  if (type === "smooth" || amt <= 0.01) return;
  const hx = h.w, hy = 1.15 * h.h, sc = 1 / h.texScale;
  const inside = (u, v) => (u / hx) ** 2 + (v / hy) ** 2 < 1.08;
  const S = (u, v, lift = 0.005) => G.pt(u, v, lift);
  ctx.save();
  poly(ctx, sil); ctx.clip();
  const grid = (step, fn) => {
    let j = 0;
    for (let v = -hy; v <= hy + 1e-6; v += step, j++) {
      let i = 0;
      for (let u = -hx; u <= hx + 1e-6; u += step, i++) if (inside(u, v)) fn(u, v, i, j);
    }
  };
  ctx.globalAlpha = amt;
  if (type === "bits") {
    grid(0.085 * sc, (u, v, i, j) => {
      const p = S(u, v); if (p.z < -0.1) return;
      const bit = Math.floor(t * 0.8 + hash(i, j) * 40) % 2 ? "1" : "0";
      const sz = 0.075 * sc * p.s;
      ctx.drawImage(glyph(bit, c2), p.x - sz / 2, p.y - sz / 2, sz, sz);
    });
  } else if (type === "pixels") {
    grid(0.08 * sc, (u, v, i, j) => {
      const p = S(u, v), sz = 0.07 * sc * p.s;
      ctx.fillStyle = hash(i, j) > 0.5 ? c2 : rgba(c2, 0.45);
      ctx.fillRect(p.x - sz / 2, p.y - sz / 2, sz, sz);
    });
  } else if (type === "dots") {
    grid(0.075 * sc, (u, v) => { const p = S(u, v); circle(ctx, p.x, p.y, 0.022 * sc * p.s); ctx.fillStyle = c2; ctx.fill(); });
  } else if (type === "poly") {
    const st = 0.2 * sc, pts = {};
    const V = (i, j) => {
      const key = i + "," + j;
      if (!pts[key]) {
        let u = -hx * 1.1 + i * st + (hash(i, j, 3) - 0.5) * st * 0.5, v = -hy * 1.1 + j * st + (hash(i, j, 5) - 0.5) * st * 0.5;
        pts[key] = { u, v, p: S(u, v, 0) };
      }
      return pts[key];
    };
    const ni = Math.ceil((2.2 * hx) / st), nj = Math.ceil((2.2 * hy) / st);
    for (let j = 0; j < nj; j++) for (let i = 0; i < ni; i++) {
      for (const tri of [[V(i, j), V(i + 1, j), V(i, j + 1)], [V(i + 1, j), V(i + 1, j + 1), V(i, j + 1)]]) {
        const cu = (tri[0].u + tri[1].u + tri[2].u) / 3, cv = (tri[0].v + tri[1].v + tri[2].v) / 3;
        const lam = clamp(0.5 - cu * 0.35 + cv * 0.35 + (hash(i, j, tri === tri ? 7 : 9) - 0.5) * 0.3);
        poly(ctx, tri.map((q) => q.p));
        ctx.fillStyle = rgba(lam > 0.5 ? "#ffffff" : c2, Math.abs(lam - 0.5) * 0.9);
        ctx.fill(); ctx.strokeStyle = rgba(c2, 0.35); ctx.lineWidth = 1; ctx.stroke();
      }
    }
  } else if (type === "stripes") {
    ctx.fillStyle = c2;
    for (let k = -4; k <= 4; k++) {
      if (k === 0) continue;
      const v0 = (k / 4.5) * hy * 0.9;
      for (const side of [-1, 1]) {
        const len = 0.35 + 0.25 * hash(k, side);
        const pts = [];
        for (let q = 0; q <= 8; q++) { const f = q / 8; pts.push(S(side * hx * (1.05 - f * len), v0 + 0.06 * sc * (1 - f) + 0.03 * Math.sin(f * 6 + k))); }
        for (let q = 8; q >= 0; q--) { const f = q / 8; pts.push(S(side * hx * (1.05 - f * len), v0 - 0.06 * sc * (1 - f) + 0.03 * Math.sin(f * 6 + k))); }
        poly(ctx, pts); ctx.fill();
      }
    }
    for (let k = 0; k < 3; k++) { const p = S((k - 1) * 0.12, hy * 0.82); oval(ctx, p.x, p.y, 0.03 * p.s, 0.11 * p.s); ctx.fill(); }
  } else if (type === "spots") {
    ctx.fillStyle = c2;
    for (let k = 0; k < 22; k++) {
      const u = (hash(k, 1, 2) * 2 - 1) * hx, v = (hash(k, 2, 2) * 2 - 1) * hy;
      if (!inside(u, v) || (Math.abs(u) < 0.55 && v > -0.6 && v < 0.35)) continue;
      const p = S(u, v), r = (0.06 + 0.1 * hash(k, 3)) * sc * p.s;
      oval(ctx, p.x, p.y, r, r * (0.7 + 0.4 * hash(k, 4)), hash(k, 5) * 3); ctx.fill();
    }
  } else if (type === "scales") {
    ctx.strokeStyle = c2; ctx.lineWidth = 1.4;
    const st = 0.11 * sc;
    grid(st, (u, v, i, j) => {
      const uu = u + (j % 2 ? st / 2 : 0), p = S(uu, v), r = st * 0.55 * p.s;
      ctx.beginPath(); ctx.arc(p.x, p.y, r, 0.1 * Math.PI, 0.9 * Math.PI); ctx.stroke();
    });
  } else if (type === "fur") {
    ctx.strokeStyle = c2; ctx.lineWidth = 1.2; ctx.lineCap = "round";
    grid(0.07 * sc, (u, v, i, j) => {
      const p = S(u, v), a = -Math.PI / 2 + Math.atan2(v, u) * 0.3 + (hash(i, j) - 0.5) * 0.8, l = 0.05 * sc * p.s;
      ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(p.x + Math.cos(a) * l, p.y + Math.sin(a) * l); ctx.stroke();
    });
  } else if (type === "wire") {
    ctx.strokeStyle = c2; ctx.lineWidth = 1;
    for (let k = -8; k <= 8; k++) {
      const v = (k / 9) * hy; ctx.beginPath();
      for (let q = 0; q <= 30; q++) { const p = S(-hx + (q / 30) * 2 * hx, v, 0); q ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y); }
      ctx.stroke();
    }
    for (let k = -8; k <= 8; k++) {
      const u = (k / 9) * hx; ctx.beginPath();
      for (let q = 0; q <= 30; q++) { const p = S(u, -hy + (q / 30) * 2 * hy, 0); q ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y); }
      ctx.stroke();
    }
  } else if (type === "lines") {
    ctx.strokeStyle = c2; ctx.lineWidth = 1.3;
    const scan = Math.sin(t * 0.9) * hy;
    for (let v = -hy; v <= hy; v += 0.055 * sc) {
      ctx.globalAlpha = amt * (0.6 + 0.4 * Math.exp(-(((v - scan) / 0.1) ** 2)) * 2);
      ctx.beginPath();
      for (let q = 0; q <= 30; q++) { const p = S(-hx + (q / 30) * 2 * hx, v, 0); q ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y); }
      ctx.stroke();
    }
  } else if (type === "hex") {
    ctx.strokeStyle = c2; ctx.lineWidth = 1.2;
    const st = 0.13 * sc;
    grid(st, (u, v, i, j) => {
      const uu = u + (j % 2 ? st / 2 : 0), pts = [];
      for (let q = 0; q < 6; q++) { const a = (q / 6) * TAU + Math.PI / 6; pts.push(S(uu + Math.cos(a) * st * 0.55, v + Math.sin(a) * st * 0.55)); }
      poly(ctx, pts); ctx.stroke();
    });
  } else if (type === "noise") {
    ctx.fillStyle = c2;
    for (let k = 0; k < 500; k++) {
      const u = (hash(k, 7) * 2 - 1) * hx, v = (hash(k, 8) * 2 - 1) * hy;
      if (!inside(u, v)) continue;
      const p = S(u, v), r = 0.008 * p.s * (0.5 + hash(k, 9));
      ctx.fillRect(p.x, p.y, r, r);
    }
  } else if (type === "stars") {
    for (let k = 0; k < 70; k++) {
      const u = (hash(k, 11) * 2 - 1) * hx, v = (hash(k, 12) * 2 - 1) * hy;
      if (!inside(u, v)) continue;
      const p = S(u, v), tw = 0.5 + 0.5 * Math.sin(t * (1 + hash(k, 13) * 3) + k);
      circle(ctx, p.x, p.y, (0.004 + 0.01 * hash(k, 14)) * p.s * (0.6 + tw));
      ctx.fillStyle = hash(k, 15) > 0.8 ? "#ffe2a3" : c2; ctx.fill();
    }
  } else if (type === "panels") {
    ctx.strokeStyle = c2; ctx.lineWidth = 1.5;
    const line = (pts) => { ctx.beginPath(); pts.forEach((q, i) => { const p = S(q[0], q[1]); i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y); }); ctx.stroke(); };
    const curve = (fn) => { const pts = []; for (let q = 0; q <= 20; q++) pts.push(fn(q / 20)); line(pts); };
    curve((f) => [-hx + f * 2 * hx, hy * 0.55]); curve((f) => [-hx + f * 2 * hx, -hy * 0.75]);
    curve((f) => [-hx * 0.85, -hy * 0.75 + f * hy * 1.3]); curve((f) => [hx * 0.85, -hy * 0.75 + f * hy * 1.3]);
    for (const [u, v] of [[-0.7, 0.65], [0.7, 0.65], [-0.7, -0.85], [0.7, -0.85]]) { const p = S(u * hx, v * hy); circle(ctx, p.x, p.y, 0.018 * p.s); ctx.fillStyle = c2; ctx.fill(); }
  } else if (type === "gradient") {
    const a = S(0, hy), b = S(0, -hy);
    const g = ctx.createLinearGradient(a.x, a.y, b.x, b.y);
    g.addColorStop(0, rgba(c2, 0)); g.addColorStop(1, rgba(c2, 1));
    ctx.fillStyle = g; poly(ctx, sil); ctx.fill();
  } else if (type === "glass") {
    const p = S(-hx * 0.35, hy * 0.5), q = S(hx * 0.4, -hy * 0.55);
    oval(ctx, p.x, p.y, 0.32 * p.s * hx, 0.13 * p.s * hy, -0.5); ctx.fillStyle = "rgba(255,255,255,.5)"; ctx.fill();
    oval(ctx, q.x, q.y, 0.18 * q.s, 0.06 * q.s, -0.6); ctx.fillStyle = "rgba(255,255,255,.25)"; ctx.fill();
    poly(ctx, sil); ctx.lineWidth = 0.04 * p.s; ctx.strokeStyle = rgba(c2, 0.8); ctx.stroke();
  }
  ctx.restore();
}

