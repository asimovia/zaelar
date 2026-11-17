// classics-more.js — classics 10 to 16 (split from classics.js by size). V2-928.
import { C, clamp, TAU, path, proj, mouthOf, circle, head, ellipse, lin, rad, along, segDist, polyDist, inPoly, logoEye, glowOn, glowOff, glyph, flatFace, byId } from "./classics-kit.js?v=1";
import { fib, HEAD } from "./rig.js?v=1";

export const MORE = [
  // ------------------------------------------------------------ 10
  {
    id: "wave", name: "Voice wave", bg: "radial-gradient(circle at 50% 42%, #0e1122, #04050a 70%)",
    draw(ctx, G) {
      const r = G.r, h = head(G), N = 110;
      ctx.lineCap = "round";
      for (let i = 0; i < N; i++) {
        const a = (i / N) * TAU + h.rot;
        const n = Math.sin(a * 5 + r.t * 2) * 0.5 + Math.sin(a * 11 - r.t * 3.3) * 0.5;
        const len = h.rx * (0.04 + 0.05 * r.glow + (0.1 + 0.12 * n) * r.energy);
        const x0 = h.x + Math.cos(a) * h.rx * 1.02, y0 = h.y + Math.sin(a) * h.ry * 1.0;
        ctx.strokeStyle = i % 2 ? C.violet : C.blue; ctx.lineWidth = Math.max(1.5, h.rx * 0.012);
        ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x0 + Math.cos(a) * len, y0 + Math.sin(a) * len); ctx.stroke();
      }
      for (const side of [-1, 1]) {
        const e = G.eye(side), c = G.P(e.iris), R = 0.11 * c.s;
        ctx.save(); ctx.translate(c.x, c.y); ctx.scale(1, Math.max(0.08, e.open));
        circle(ctx, 0, 0, R); ctx.lineWidth = Math.max(2, 0.025 * c.s); ctx.strokeStyle = C.iris; ctx.stroke();
        circle(ctx, 0, 0, R * 0.45); ctx.fillStyle = rad(ctx, 0, 0, 0, R * 0.45, [C.core, C.amber, C.orange]); ctx.fill();
        ctx.restore();
      }
      const m = G.mouth(), a = G.P([-m.mw - 0.06, m.my]), b = G.P([m.mw + 0.06, m.my]);
      glowOn(ctx, C.amber, 14); ctx.strokeStyle = C.amber; ctx.lineWidth = Math.max(2, 0.025 * a.s);
      ctx.beginPath();
      for (let i = 0; i <= 60; i++) {
        const k = i / 60, env = Math.sin(Math.PI * k);
        const y = Math.sin(k * 26 + r.t * 14) * 0.6 + Math.sin(k * 11 - r.t * 9) * 0.4;
        const amp = (0.004 + 0.13 * r.open) * a.s;
        const x = a.x + (b.x - a.x) * k, yy = a.y + (b.y - a.y) * k + y * amp * env - r.smile * 0.05 * a.s * env;
        i ? ctx.lineTo(x, yy) : ctx.moveTo(x, yy);
      }
      ctx.stroke(); glowOff(ctx);
    },
  },
  // ------------------------------------------------------------ 11
  {
    id: "bubble", name: "Bubble", bg: "radial-gradient(circle at 50% 40%, #1b1640, #08061a 72%)",
    draw(ctx, G) {
      const r = G.r, h = head(G);
      glowOn(ctx, "rgba(120,90,255,.5)", h.rx * 0.3);
      ellipse(ctx, h, 1.0);
      ctx.fillStyle = rad(ctx, h.x - h.rx * 0.3, h.y - h.ry * 0.4, h.rx * 0.1, h.rx * 1.3, ["#e3d9ff", "#a995ff", "#6c5ce7", "#3b2a9e"]);
      ctx.fill(); glowOff(ctx);
      ellipse(ctx, { ...h, x: h.x - h.rx * 0.35, y: h.y - h.ry * 0.55, rx: h.rx * 0.32, ry: h.ry * 0.14, rot: h.rot - 0.5 });
      ctx.fillStyle = "rgba(255,255,255,.35)"; ctx.fill();
      for (const side of [-1, 1]) {
        const e = G.eye(side), c = G.P(e.iris), w = 0.12 * c.s, hh = Math.max(0.012 * c.s, 0.17 * c.s * e.open);
        ellipse(ctx, { x: c.x, y: c.y, rx: w, ry: hh, rot: h.rot }); ctx.fillStyle = "#1a1340"; ctx.fill();
        if (e.open > 0.3) {
          circle(ctx, c.x, c.y + hh * 0.15, w * 0.42); ctx.fillStyle = rad(ctx, c.x, c.y, 0, w * 0.42, [C.core, C.amber, C.orange]); ctx.fill();
          circle(ctx, c.x - w * 0.35, c.y - hh * 0.4, w * 0.18); ctx.fillStyle = "#fff"; ctx.fill();
        }
        const ch = G.P([side * 0.55, -0.2]);
        ellipse(ctx, { x: ch.x, y: ch.y, rx: 0.13 * ch.s, ry: 0.07 * ch.s, rot: h.rot });
        ctx.fillStyle = `rgba(255,120,190,${0.2 + 0.25 * clamp(r.smile)})`; ctx.fill();
      }
      const mo = mouthOf(G);
      path(ctx, mo.all, true); ctx.fillStyle = "#1a1340"; ctx.fill();
      if (r.open > 0.25) {
        ctx.save(); path(ctx, mo.all, true); ctx.clip();
        const lp = G.P([0, mo.m.my - mo.m.h * 0.75]);
        ellipse(ctx, { x: lp.x, y: lp.y, rx: mo.m.mw * 0.55 * lp.s, ry: mo.m.h * 0.45 * lp.s, rot: h.rot }); ctx.fillStyle = "#ff7eb6"; ctx.fill();
        ctx.restore();
      }
      ctx.lineWidth = Math.max(2, 0.03 * mo.up[0].s); ctx.lineJoin = ctx.lineCap = "round"; ctx.strokeStyle = "#1a1340"; ctx.stroke();
    },
  },
  // ------------------------------------------------------------ 12
  {
    id: "pixel", name: "Pixel 8-bit", bg: "#0d0b1e",
    draw(ctx, G, W, H) {
      const h = head(G), N = 34, size = h.ry * 2.5;
      const off = this._c || (this._c = document.createElement("canvas"));
      off.width = off.height = N;
      const o = off.getContext("2d"); o.clearRect(0, 0, N, N);
      byId("bubble").draw(o, G.with(N / 2, N / 2, N / 2.6), N, N);   // the bubble face, resampled to 8-bit
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(off, h.x - size / 2, h.y - size / 2, size, size);
      ctx.imageSmoothingEnabled = true;
    },
  },
  // ------------------------------------------------------------ 13
  {
    id: "ascii", name: "ASCII terminal", bg: "#020604",
    draw(ctx, G) {
      const h = head(G), cols = 52, rows = 34, size = h.ry * 2.45;
      const off = this._c || (this._c = document.createElement("canvas"));
      off.width = cols; off.height = rows;
      const o = off.getContext("2d", { willReadFrequently: true }); o.clearRect(0, 0, cols, rows);
      o.save(); o.scale(1, rows / cols);
      const g = G.with(cols / 2, cols / 2, cols / 2.7), hh = head(g);
      ellipse(o, hh); o.fillStyle = "#2a2a2a"; o.fill();
      o.lineWidth = 1.2; o.strokeStyle = "#555"; o.stroke();
      o.fillStyle = "#fff"; o.strokeStyle = "#fff"; o.lineWidth = 1.6; o.lineCap = o.lineJoin = "round";
      for (const side of [-1, 1]) {
        const e = g.eye(side), c = g.P(e.iris);
        path(o, proj(g, e.outline), true); o.stroke();
        if (e.open > 0.25) { circle(o, c.x, c.y, e.irisR * c.s); o.fill(); }
        path(o, proj(g, g.brow(side))); o.stroke();
      }
      const mo = mouthOf(g); path(o, mo.all, true); o.stroke();
      o.restore();
      const d = o.getImageData(0, 0, cols, rows).data, ramp = " .:-=+*#%@";
      const cw = size / cols, chH = size / rows;
      ctx.font = `bold ${Math.round(chH * 1.05)}px ui-monospace, Menlo, monospace`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) {
        const i = (y * cols + x) * 4;
        if (d[i + 3] < 40) continue;
        const l = (d[i] + d[i + 1] + d[i + 2]) / 765;
        if (l < 0.08) continue;
        const ch = ramp[Math.min(ramp.length - 1, Math.floor(l * ramp.length))];
        ctx.fillStyle = l > 0.9 ? "#c6ffd8" : l < 0.15 ? "#1d6b3e" : "#3cf08a";
        ctx.fillText(ch, h.x - size / 2 + (x + 0.5) * cw, h.y - size / 2 + (y + 0.5) * chH);
      }
    },
  },
  // ------------------------------------------------------------ 14
  {
    id: "swarm", name: "Swarm", bg: "radial-gradient(circle at 50% 42%, #0c0f22, #030409 70%)",
    draw(ctx, G) {
      const r = G.r, shell = fib(900);
      const feat = [];
      const s0 = G.P([0, 0]).s;
      for (const side of [-1, 1]) {
        const e = G.eye(side);
        for (const p of along(proj(G, e.outline), 0.02 * s0)) feat.push([p, C.cyan]);
        const c = G.P(e.iris);
        if (e.open > 0.25) for (let k = 0; k < 26; k++) {
          const a = k * 2.4, rr = Math.sqrt(k / 26) * e.irisR * c.s;
          feat.push([{ x: c.x + Math.cos(a) * rr, y: c.y + Math.sin(a) * rr * e.open }, k < 9 ? C.amber : C.iris]);
        }
        for (const p of along(proj(G, G.brow(side)), 0.025 * s0)) feat.push([p, C.violet]);
      }
      const mo = mouthOf(G);
      for (const p of along(mo.up, 0.02 * s0)) feat.push([p, C.cyan]);
      for (const p of along(mo.lo, 0.02 * s0)) feat.push([p, C.cyan]);
      const N = shell.length + 420;
      if (!this._p || this._p.length !== N) this._p = Array.from({ length: N }, () => ({ x: G.cx, y: G.cy, vx: 0, vy: 0 }));
      ctx.globalCompositeOperation = "lighter";
      for (let i = 0; i < N; i++) {
        const p = this._p[i];
        let tx, ty, col, a = 0.8, sz = 0.012 * s0;
        if (i < shell.length) {
          const [x, y, z, seed] = shell[i], q = G.proj(x * HEAD.x, y * HEAD.y, z * HEAD.z);
          tx = q.x; ty = q.y; col = seed > 0.5 ? C.blue : C.violet; a = q.z < 0 ? 0.08 : 0.15 + 0.4 * q.z;
          if (z > 0.55 && Math.abs(x) < 0.7 && y > -0.75 && y < 0.45) a *= 0.35;
        } else {
          const f = feat[(i - shell.length) % Math.max(1, feat.length)];
          if (!f) continue;
          tx = f[0].x; ty = f[0].y; col = f[1]; sz *= 1.3;
        }
        const jit = (0.002 + 0.02 * r.energy) * s0;
        p.vx = (p.vx + (tx - p.x) * 0.12) * 0.62 + (Math.random() - 0.5) * jit;
        p.vy = (p.vy + (ty - p.y) * 0.12) * 0.62 + (Math.random() - 0.5) * jit;
        p.x += p.vx; p.y += p.vy;
        ctx.globalAlpha = a; ctx.fillStyle = col; ctx.fillRect(p.x - sz / 2, p.y - sz / 2, sz, sz);
      }
      ctx.globalAlpha = 1; ctx.globalCompositeOperation = "source-over";
    },
  },
  // ------------------------------------------------------------ 15
  {
    id: "lowpoly", name: "Low-poly", bg: "radial-gradient(circle at 50% 42%, #10142a, #04050c 70%)",
    draw(ctx, G) {
      const r = G.r, nu = 12, nv = 14;
      const V = [];
      for (let j = 0; j <= nv; j++) {
        V.push([]);
        for (let i = 0; i <= nu; i++) {
          let u = (i / nu) * 2 - 1, v = (j / nv) * 2.3 - 1.15;
          const seed = Math.sin(i * 12.9898 + j * 78.233) * 43758.5453;
          u += ((seed - Math.floor(seed)) - 0.5) * 0.06; v += ((seed * 1.7 - Math.floor(seed * 1.7)) - 0.5) * 0.06;
          const e2 = (u / HEAD.x) ** 2 + (v / HEAD.y) ** 2;
          if (e2 > 0.97) { const k = Math.sqrt(0.97 / e2); u *= k; v *= k; }   // pull rim vertices onto the outline
          V[j].push({ u, v, ok: true, z: G.surfZ(u, v) });
        }
      }
      const L = [-0.4, 0.5, 0.75];
      const tri = (a, b, c) => {
        if (!a.ok || !b.ok || !c.ok) return;
        const nx = (a.u + b.u + c.u) / 3 / HEAD.x ** 2, ny = (a.v + b.v + c.v) / 3 / HEAD.y ** 2, nz = (a.z + b.z + c.z) / 3 / HEAD.z ** 2;
        const nl = Math.hypot(nx, ny, nz), lam = clamp((nx * L[0] + ny * L[1] + nz * L[2]) / nl);
        const pa = G.proj(a.u, a.v, a.z), pb = G.proj(b.u, b.v, b.z), pc = G.proj(c.u, c.v, c.z);
        ctx.beginPath(); ctx.moveTo(pa.x, pa.y); ctx.lineTo(pb.x, pb.y); ctx.lineTo(pc.x, pc.y); ctx.closePath();
        const k = 0.25 + 0.75 * lam;
        ctx.fillStyle = `rgb(${Math.round(40 + 90 * k)},${Math.round(40 + 60 * k)},${Math.round(110 + 130 * k)})`;
        ctx.fill(); ctx.strokeStyle = "rgba(180,170,255,.18)"; ctx.lineWidth = 1; ctx.stroke();
      };
      for (let j = 0; j < nv; j++) for (let i = 0; i < nu; i++) {
        tri(V[j][i], V[j][i + 1], V[j + 1][i]); tri(V[j][i + 1], V[j + 1][i + 1], V[j + 1][i]);
      }
      for (const side of [-1, 1]) logoEye(ctx, G, G.eye(side), 1.1, { fill: "#0a0c1c" });
      const mo = mouthOf(G, 0.04);
      path(ctx, mo.all, true); ctx.fillStyle = "#0a0c1c"; ctx.fill();
      ctx.lineWidth = Math.max(1.5, 0.025 * mo.up[0].s); ctx.strokeStyle = C.amber; ctx.stroke();
    },
  },
  // ------------------------------------------------------------ 16
  {
    id: "mono", name: "Minimal", bg: "#000",
    draw(ctx, G) {
      const r = G.r, h = head(G);
      ellipse(ctx, h); ctx.strokeStyle = "rgba(255,255,255,.12)"; ctx.lineWidth = 1.5; ctx.stroke();
      ctx.fillStyle = "#fff";
      for (const side of [-1, 1]) {
        const e = G.eye(side), c = G.P(e.iris), rr = 0.065 * c.s;
        ellipse(ctx, { x: c.x, y: c.y, rx: rr, ry: Math.max(rr * 0.12, rr * e.open), rot: h.rot }); ctx.fill();
      }
      const mo = mouthOf(G);
      path(ctx, mo.all, true); ctx.lineWidth = Math.max(2, 0.035 * mo.up[0].s); ctx.lineJoin = ctx.lineCap = "round";
      ctx.strokeStyle = "#fff"; ctx.stroke();
    },
  },
];
