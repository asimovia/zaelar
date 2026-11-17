// classics.js — the 17 classic faces (Porcelain first, the default; its drawing is never changed). Each style only DRAWS: the rig (rig.js) decides where the lips, eyes, brows
// and head are, so lip sync, blinks and gestures are identical in every style and only the look changes.
// draw(ctx, G, W, H): G = geometry for this frame (G.r = rig numbers, G.P(uv) projects a face point).
import { C, clamp, TAU, path, proj, mouthOf, circle, head, ellipse, lin, rad, along, segDist, polyDist, inPoly, logoEye, glowOn, glowOff, glyph, flatFace, byId, ALL } from "./classics-kit.js?v=1";
import { fib, HEAD } from "./rig.js?v=1";
import { MORE } from "./classics-more.js?v=1";

export const STYLES = [
  // ------------------------------------------------------------ 17
  {
    id: "porcelain", name: "Porcelain", bg: "radial-gradient(circle at 50% 40%, #f4f6fb, #d9dee8 75%)",
    draw(ctx, G) {
      const r = G.r, h = head(G);
      ctx.save(); ctx.shadowColor = "rgba(40,50,80,.25)"; ctx.shadowBlur = h.rx * 0.25; ctx.shadowOffsetY = h.rx * 0.08;
      ellipse(ctx, h);
      ctx.fillStyle = rad(ctx, h.x - h.rx * 0.3, h.y - h.ry * 0.4, h.rx * 0.1, h.rx * 1.4, ["#ffffff", "#eef1f7", "#cfd6e4", "#aab3c6"]);
      ctx.fill(); ctx.restore();
      for (const side of [-1, 1]) {
        const e = G.eye(side), c = G.P(e.iris), w = 0.085 * c.s, hh = Math.max(0.01 * c.s, 0.12 * c.s * e.open);
        ellipse(ctx, { x: c.x, y: c.y, rx: w, ry: hh, rot: h.rot }); ctx.fillStyle = "#1e2433"; ctx.fill();
        if (e.open > 0.3) {
          circle(ctx, c.x, c.y, w * 0.32); ctx.fillStyle = r.speaking ? C.amber : "#6b7cff"; ctx.fill();
          circle(ctx, c.x - w * 0.35, c.y - hh * 0.45, w * 0.16); ctx.fillStyle = "rgba(255,255,255,.85)"; ctx.fill();
        }
      }
      const mo = mouthOf(G);
      path(ctx, mo.all, true); ctx.fillStyle = "#2a3142"; ctx.fill();
      ctx.lineWidth = Math.max(2, 0.025 * mo.up[0].s); ctx.lineJoin = ctx.lineCap = "round"; ctx.strokeStyle = "#2a3142"; ctx.stroke();
    },
  },
  // ------------------------------------------------------------ 1
  {
    id: "logo", name: "Zaelar eye", bg: "radial-gradient(circle at 50% 42%, #111a33, #05070e 70%)",
    draw(ctx, G) {
      const r = G.r, h = head(G), t = r.t;
      // the logo's four arcs + two dots as the head, slowly turning
      ctx.save(); ctx.translate(h.x, h.y); ctx.rotate(t * 0.08 + h.rot);
      ctx.lineCap = "round"; ctx.lineWidth = Math.max(2, h.rx * 0.035);
      ctx.strokeStyle = lin(ctx, -h.rx, 0, h.rx, 0, [C.blue, C.violet]);
      glowOn(ctx, "rgba(150,120,255,.6)", 20 * r.glow);
      const R = h.ry * 0.98;
      for (let q = 0; q < 4; q++) { ctx.beginPath(); ctx.arc(0, 0, R, q * TAU / 4 + 0.32, (q + 1) * TAU / 4 - 0.32); ctx.stroke(); }
      ctx.fillStyle = C.violet;
      for (const sy of [-1, 1]) { circle(ctx, 0, sy * R, h.rx * 0.045); ctx.fill(); }
      ctx.restore(); glowOff(ctx);
      for (const side of [-1, 1]) logoEye(ctx, G, G.eye(side), 1.3, { fill: "rgba(10,14,30,.85)" });
      const mo = mouthOf(G);
      path(ctx, mo.all, true); ctx.fillStyle = "rgba(255,177,74,.18)"; ctx.fill();
      ctx.lineWidth = Math.max(2, 0.03 * mo.up[0].s); ctx.lineJoin = "round";
      ctx.strokeStyle = lin(ctx, mo.up[0].x, 0, mo.up[mo.up.length - 1].x, 0, [C.blue, C.amber, C.violet]);
      glowOn(ctx, C.amber, 12 * r.glow); ctx.stroke(); glowOff(ctx);
    },
  },
  // ------------------------------------------------------------ 2
  {
    id: "orb", name: "Friendly orb", bg: "radial-gradient(circle at 50% 40%, #16122b, #06060d 70%)",
    draw(ctx, G) {
      const r = G.r, h = head(G), Rr = Math.min(h.rx, h.ry) * 1.02;
      ctx.save();
      glowOn(ctx, "rgba(140,110,255,.7)", Rr * 0.35 * r.glow);
      circle(ctx, h.x, h.y, Rr);
      ctx.fillStyle = rad(ctx, h.x - Rr * 0.3, h.y - Rr * 0.35, Rr * 0.05, Rr * 1.05, ["#b9c8ff", "#7b6bff", "#4a2fb8", "#1d1450"]);
      ctx.fill(); ctx.restore();
      circle(ctx, h.x - Rr * 0.32, h.y - Rr * 0.42, Rr * 0.22); ctx.fillStyle = "rgba(255,255,255,.12)"; ctx.fill();
      glowOn(ctx, r.speaking ? C.core : "#ffffff", 18);
      ctx.fillStyle = "#ffffff";
      for (const side of [-1, 1]) {
        const e = G.eye(side), c = G.P(e.iris), w = 0.075 * c.s, hh = Math.max(w * 0.35, 0.17 * c.s * e.open);
        ctx.beginPath(); ctx.roundRect(c.x - w / 2, c.y - hh / 2, w, hh, w / 2); ctx.fill();
      }
      const mo = mouthOf(G);
      path(ctx, mo.all, true); ctx.fillStyle = "rgba(20,10,60,.55)"; ctx.fill();
      ctx.lineWidth = Math.max(2, 0.045 * mo.up[0].s); ctx.lineCap = ctx.lineJoin = "round"; ctx.strokeStyle = "#fff";
      ctx.stroke(); glowOff(ctx);
    },
  },
  // ------------------------------------------------------------ 3
  {
    id: "binary", name: "Bits 0/1", bg: "radial-gradient(circle at 50% 42%, #08111f, #020409 70%)",
    draw(ctx, G) {
      const r = G.r, t = r.t, pts = fib(760);
      for (const [x, y, z, seed] of pts) {
        const p = G.proj(x * HEAD.x, y * HEAD.y, z * HEAD.z);
        if (p.z < -0.25) continue;
        const facing = clamp((p.z + 0.25) / 1.15);
        let a = (0.12 + 0.6 * facing) * (0.55 + 0.45 * r.glow);
        if (z > 0.55 && Math.abs(x) < 0.7 && y > -0.75 && y < 0.45) a *= 0.3;   // let the features read
        const bit = Math.floor(t * (0.8 + r.energy * 7) + seed * 40) % 2 ? "1" : "0";
        const col = y + seed * 0.4 > 0.25 ? C.violet : seed > 0.85 ? C.amber : C.blue;
        const sz = 0.075 * p.s;
        ctx.globalAlpha = a; ctx.drawImage(glyph(bit, col), p.x - sz / 2, p.y - sz / 2, sz, sz);
      }
      ctx.globalAlpha = 1;
      const s0 = G.P([0, 0]).s, step = 0.05 * s0, sz = 0.07 * s0;
      const put = (p, ch, col, k = 1) => ctx.drawImage(glyph(ch, col), p.x - (sz * k) / 2, p.y - (sz * k) / 2, sz * k, sz * k);
      let i = 0;
      const bit = () => (Math.floor(t * 4 + i++ * 0.7) % 2 ? "1" : "0");
      for (const side of [-1, 1]) {
        const e = G.eye(side);
        for (const p of along(proj(G, e.outline), step)) put(p, bit(), C.cyan);
        const c = G.P(e.iris);
        if (e.open > 0.25) {
          for (let k = 0; k < 10; k++) {
            const a = (k / 10) * TAU;
            put({ x: c.x + Math.cos(a) * e.irisR * c.s, y: c.y + Math.sin(a) * e.irisR * c.s * Math.min(1, e.open * 1.4) }, bit(), C.iris, 0.8);
          }
          put(c, "1", C.amber, 1.5);
        }
        for (const p of along(proj(G, G.brow(side)), step)) put(p, bit(), C.blue, 0.85);
      }
      const mo = mouthOf(G);
      for (const p of along(mo.up, step * 0.9)) put(p, bit(), C.cyan);
      for (const p of along(mo.lo, step * 0.9)) put(p, bit(), C.cyan);
    },
  },
  // ------------------------------------------------------------ 4
  {
    id: "led", name: "LED matrix", bg: "#05070c",
    draw(ctx, G) {
      const r = G.r, cols = 33, rows = 37;
      const eyes = [-1, 1].map((s) => G.eye(s)), brows = [-1, 1].map((s) => G.brow(s)), m = G.mouth();
      const mouthPoly = m.upper.concat(m.lower.slice().reverse());
      for (let j = 0; j < rows; j++) {
        for (let i = 0; i < cols; i++) {
          const u = (i / (cols - 1)) * 2 - 1, v = ((rows - 1 - j) / (rows - 1)) * 2.3 - 1.15;
          if ((u / HEAD.x) ** 2 + (v / HEAD.y) ** 2 > 0.93) continue;
          const p = G.pt(u, v, 0.01);
          let col = null;
          for (const e of eyes) {
            const di = Math.hypot(u - e.iris[0], (v - e.iris[1]) / Math.max(0.15, e.open));
            if (polyDist(u, v, e.outline) < 0.034) col = C.cyan;
            else if (e.open > 0.2 && inPoly(u, v, e.outline)) col = di < e.coreR * 1.2 ? C.amber : di < e.irisR * 1.15 ? C.iris : null;
          }
          for (const b of brows) if (polyDist(u, v, b) < 0.03) col = C.blue;
          if (polyDist(u, v, m.upper) < 0.034 || polyDist(u, v, m.lower) < 0.034) col = C.cyan;
          else if (m.h > 0.05 && inPoly(u, v, mouthPoly)) col = "rgba(56,217,255,.35)";
          const rr = 0.026 * p.s;
          circle(ctx, p.x, p.y, rr);
          if (col) {
            ctx.fillStyle = col; ctx.fill();
            circle(ctx, p.x, p.y, rr * 2.1); ctx.fillStyle = col === C.amber ? "rgba(255,177,74,.18)" : "rgba(56,217,255,.12)"; ctx.fill();
          } else { ctx.fillStyle = `rgba(40,60,110,${0.25 + 0.2 * r.glow})`; ctx.fill(); }
        }
      }
    },
  },
  // ------------------------------------------------------------ 5
  {
    id: "visor", name: "Robot visor", bg: "radial-gradient(circle at 50% 40%, #0f1626, #04060b 72%)",
    draw(ctx, G) {
      const r = G.r, plane = (u, v) => G.proj(u, v, 0.92);
      const quad = (u0, v0, u1, v1) => [plane(u0, v0), plane(u1, v0), plane(u1, v1), plane(u0, v1)];
      // helmet
      const h = head(G);
      ctx.beginPath(); ctx.roundRect(h.x - h.rx * 1.02, h.y - h.ry * 0.95, h.rx * 2.04, h.ry * 1.9, h.rx * 0.75);
      ctx.fillStyle = lin(ctx, 0, h.y - h.ry, 0, h.y + h.ry, ["#2a3352", "#141a2e", "#0a0d18"]); ctx.fill();
      ctx.lineWidth = Math.max(1.5, h.rx * 0.015); ctx.strokeStyle = "rgba(140,170,255,.35)"; ctx.stroke();
      // visor screen
      const tl = plane(-0.72, 0.42), br = plane(0.72, -0.7);
      ctx.beginPath(); ctx.roundRect(tl.x, tl.y, br.x - tl.x, br.y - tl.y, (br.x - tl.x) * 0.16);
      ctx.fillStyle = "#03050b"; ctx.fill();
      ctx.strokeStyle = "rgba(79,140,255,.5)"; ctx.lineWidth = Math.max(1, h.rx * 0.01); ctx.stroke();
      glowOn(ctx, C.cyan, 16 * r.glow); ctx.fillStyle = C.cyan; ctx.strokeStyle = C.cyan; ctx.lineCap = "round";
      for (const side of [-1, 1]) {
        const e = G.eye(side), cx = side * 0.36 + r.gazeX * 0.06, cy = 0.1 + r.gazeY * 0.04;
        const happy = r.smile > 0.55;
        if (happy && e.open > 0.3) {
          const a = plane(cx - 0.12, cy - 0.04), b = plane(cx, cy + 0.08), c = plane(cx + 0.12, cy - 0.04);
          ctx.lineWidth = 0.05 * b.s; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.quadraticCurveTo(b.x, b.y - 0.04 * b.s, c.x, c.y); ctx.stroke();
        } else {
          const hh = Math.max(0.02, 0.2 * e.open);
          path(ctx, quad(cx - 0.1, cy + hh / 2, cx + 0.1, cy - hh / 2), true); ctx.fill();
        }
      }
      // mouth: an equalizer while speaking, a soft smile line otherwise
      const bars = 7;
      for (let k = 0; k < bars; k++) {
        const x = (k - (bars - 1) / 2) * 0.055;
        const amp = r.open * (0.55 + 0.45 * Math.sin(r.t * 18 + k * 1.7)) * (1 - Math.abs(k - 3) / 5);
        const hh = 0.02 + 0.26 * amp, y = -0.42 + r.smile * 0.04 * ((x / 0.2) ** 2);
        path(ctx, quad(x - 0.018, y + hh / 2, x + 0.018, y - hh / 2), true); ctx.fill();
      }
      glowOff(ctx);
    },
  },
  // ------------------------------------------------------------ 6
  {
    id: "wire", name: "Wireframe", bg: "radial-gradient(circle at 50% 42%, #0a1424, #02050b 70%)",
    draw(ctx, G) {
      const r = G.r;
      ctx.lineWidth = 1;
      const ring = (fn, n) => {
        let prev = null;
        for (let i = 0; i <= n; i++) {
          const p = fn(i / n);
          if (prev) {
            const z = (p.z + prev.z) / 2;
            ctx.strokeStyle = z > 0 ? `rgba(56,217,255,${0.15 + 0.45 * z * r.glow})` : "rgba(79,140,255,.07)";
            ctx.beginPath(); ctx.moveTo(prev.x, prev.y); ctx.lineTo(p.x, p.y); ctx.stroke();
          }
          prev = p;
        }
      };
      for (let k = -8; k <= 8; k++) {
        const v = (k / 9) * HEAD.y, q = Math.sqrt(1 - (v / HEAD.y) ** 2);
        ring((s) => G.proj(Math.cos(s * TAU) * HEAD.x * q, v, Math.sin(s * TAU) * HEAD.z * q), 48);
      }
      for (let k = 0; k < 12; k++) {
        const a = (k / 12) * Math.PI;
        ring((s) => { const b = s * TAU; return G.proj(Math.cos(a) * Math.sin(b) * HEAD.x, Math.cos(b) * HEAD.y, Math.sin(a) * Math.sin(b) * HEAD.z); }, 48);
      }
      glowOn(ctx, C.violet, 12);
      for (const side of [-1, 1]) logoEye(ctx, G, G.eye(side), 1, { fill: "rgba(3,6,14,.9)" });
      const mo = mouthOf(G, 0.03);
      path(ctx, mo.all, true); ctx.fillStyle = "rgba(3,6,14,.9)"; ctx.fill();
      ctx.lineWidth = Math.max(1.5, 0.022 * mo.up[0].s); ctx.strokeStyle = C.amber; ctx.stroke();
      for (const side of [-1, 1]) { path(ctx, proj(G, G.brow(side), 0.03)); ctx.strokeStyle = C.violet; ctx.stroke(); }
      glowOff(ctx);
    },
  },
  // ------------------------------------------------------------ 7
  {
    id: "slices", name: "Hologram", bg: "radial-gradient(circle at 50% 45%, #0b1630, #02040a 72%)",
    draw(ctx, G) {
      const r = G.r, scan = Math.sin(r.t * 0.9) * HEAD.y;
      ctx.lineWidth = 1.4;
      for (let k = -20; k <= 20; k++) {
        const v = (k / 21) * HEAD.y, q = Math.sqrt(1 - (v / HEAD.y) ** 2);
        const hot = Math.exp(-(((v - scan) / 0.12) ** 2));
        const tcol = (v / HEAD.y + 1) / 2;
        const col = tcol > 0.5 ? [179, 102, 255] : [56, 217, 255];
        ctx.beginPath();
        for (let i = 0; i <= 40; i++) {
          const a = (i / 40) * Math.PI;  // the front half only
          const p = G.proj(Math.cos(a) * HEAD.x * q, v, Math.sin(a) * HEAD.z * q);
          i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y);
        }
        ctx.strokeStyle = `rgba(${col[0]},${col[1]},${col[2]},${0.18 + 0.35 * r.glow * q + 0.5 * hot})`;
        ctx.stroke();
      }
      glowOn(ctx, C.cyan, 14);
      for (const side of [-1, 1]) logoEye(ctx, G, G.eye(side), 1, { fill: "rgba(2,6,16,.85)", stroke: C.cyan });
      const mo = mouthOf(G, 0.04);
      path(ctx, mo.all, true); ctx.fillStyle = "rgba(2,6,16,.85)"; ctx.fill();
      ctx.lineWidth = Math.max(1.5, 0.025 * mo.up[0].s); ctx.strokeStyle = C.cyan; ctx.stroke();
      glowOff(ctx);
    },
  },
  // ------------------------------------------------------------ 8
  {
    id: "neon", name: "Neon", bg: "radial-gradient(circle at 50% 40%, #1a0b2e, #07020d 72%)",
    draw(ctx, G) {
      const r = G.r, h = head(G);
      ctx.lineCap = ctx.lineJoin = "round";
      const stroke = (w, col, blur) => { ctx.lineWidth = w; ctx.strokeStyle = col; glowOn(ctx, typeof col === "string" ? col : C.pink, blur); ctx.stroke(); };
      ellipse(ctx, h); stroke(Math.max(2, h.rx * 0.03), lin(ctx, h.x, h.y - h.ry, h.x, h.y + h.ry, [C.pink, C.violet, C.cyan]), 30 * r.glow + 8);
      for (const side of [-1, 1]) {
        const e = G.eye(side), ol = proj(G, e.outline), ic = G.P(e.iris);
        path(ctx, ol, true); stroke(Math.max(2, 0.03 * ic.s), C.pink, 18);
        if (e.open > 0.2) {
          ctx.save(); path(ctx, ol, true); ctx.clip();
          circle(ctx, ic.x, ic.y, e.irisR * ic.s); stroke(Math.max(2, 0.03 * ic.s), C.cyan, 16);
          circle(ctx, ic.x, ic.y, e.coreR * ic.s * 0.7); ctx.fillStyle = C.core; glowOn(ctx, C.amber, 20); ctx.fill();
          ctx.restore();
        }
        path(ctx, proj(G, G.brow(side))); stroke(Math.max(2, 0.03 * ic.s), C.cyan, 14);
      }
      const mo = mouthOf(G);
      path(ctx, mo.all, true); stroke(Math.max(2, 0.035 * mo.up[0].s), C.amber, 22);
      glowOff(ctx);
    },
  },
  // ------------------------------------------------------------ 9
  {
    id: "constellation", name: "Constellation", bg: "radial-gradient(circle at 50% 42%, #0a1020, #020308 70%)",
    draw(ctx, G) {
      const r = G.r, nodes = [];
      for (const [x, y, z] of fib(120)) {
        const p = G.proj(x * HEAD.x, y * HEAD.y, z * HEAD.z);
        if (p.z > -0.1) nodes.push({ ...p, c: C.blue, w: 0.6 + 0.4 * p.z });
      }
      for (const side of [-1, 1]) {
        const e = G.eye(side);
        e.outline.filter((_, i) => i % 3 === 0).forEach((uv) => nodes.push({ ...G.P(uv), c: C.cyan, w: 1 }));
        nodes.push({ ...G.P(e.iris), c: C.amber, w: 1.8, core: true });
        G.brow(side).filter((_, i) => i % 3 === 0).forEach((uv) => nodes.push({ ...G.P(uv), c: C.violet, w: 1 }));
      }
      const m = G.mouth();
      m.upper.concat(m.lower).filter((_, i) => i % 3 === 0).forEach((uv) => nodes.push({ ...G.P(uv), c: C.cyan, w: 1 }));
      const maxD = nodes[0] ? nodes[0].s * 0.36 : 50;
      ctx.lineWidth = 1;
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j], d = Math.hypot(a.x - b.x, a.y - b.y);
          if (d < maxD) {
            ctx.strokeStyle = `rgba(110,150,255,${(1 - d / maxD) * 0.75 * Math.min(a.w, b.w) * (0.6 + 0.4 * r.glow)})`;
            ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
          }
        }
      }
      for (const n of nodes) {
        circle(ctx, n.x, n.y, (n.core ? 0.04 : 0.016) * n.s * n.w * (1 + r.energy * 0.4));
        ctx.fillStyle = n.c; ctx.fill();
      }
    },
  },
  ...MORE,
];
ALL.push(...STYLES);
