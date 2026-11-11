// ============================================================================
// boot-anim.js — the ONE loader's growth (V2-881): «Synaptic hive».
//
// The operator's shape (2026-11-11): a small ring of dots turning in the centre; from there the neurons GROW
// outwards in discrete steps («pa, pa, pa») until they fill the screen; the growth itself is the progress bar; and
// it ALWAYS finishes — when the system is ready, whatever step it reached, the rest of the growth bursts out in well
// under a second and the veil lifts.
//
// THE HONESTY RULE (see core/preboot.js): a step is a REAL boot phase, never a clock. `setStage(n)` is the only thing
// that grows the mesh, and `finish()` — called on `store.bootReady` — is the only thing that completes it. Between
// two phases the mesh breathes (glow, drift, the ring turning) but does not grow: a wait shows as a wait.
//
// Pure <canvas>, no deps; colours from the --hb-* tokens; honours prefers-reduced-motion.
// Contract: startBootAnim(canvas) → { setStage(n), finish(onDone), shown(), destroy() }.
// ============================================================================

/** Fraction of the mesh (beyond the ring) shown at each stage — 0 the ring (HTML), 1 the engine answers /healthz,
 *  2 the interface is loaded, 3 voice, 4 memory, 5 reflex, 6 ready. Exported: BootOverlay reports it as the bar. */
export const STAGE_REVEAL = [0, 0.1, 0.24, 0.42, 0.6, 0.8, 1];
export const STAGE_READY = STAGE_REVEAL.length - 1;
export const BURST_MS = 380;      // the burst: every piece left appears in this window, then the veil fades
const RING_N = 8;                 // the dots of the first ring — the same eight the HTML paints before any module
const RING_R = 22;                // px; equals `.pb-ring` in core/shared-surfaces.css
const RING_PERIOD = 2.4;          // seconds per turn; equals the `pb-turn` animation
const NODE_COUNT = 220;
const POP_S = 0.22;               // how long one piece takes to appear
const BAND_S = 0.26;              // a whole step lands within this window: «pa»

function cssRGB(name, fallback) {
  const s = (getComputedStyle(document.documentElement).getPropertyValue(name) || "").trim() || fallback;
  const m6 = s.match(/^#([0-9a-f]{6})$/i);
  if (m6) return [0, 2, 4].map((i) => parseInt(m6[1].slice(i, i + 2), 16));
  const m = s.match(/rgba?\(([^)]+)\)/i);
  return m ? m[1].split(",").slice(0, 3).map((n) => parseInt(n, 10)) : [120, 140, 170];
}
const rgba = ([r, g, b], a) => `rgba(${r | 0},${g | 0},${b | 0},${a})`;
const mix = (a, b, t) => [0, 1, 2].map((i) => a[i] + (b[i] - a[i]) * t);
const easeOut = (t) => 1 - Math.pow(1 - t, 3);

export function startBootAnim(canvas) {
  const ctx = canvas.getContext("2d");
  const reduced = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const accent = cssRGB("--hb-accent", "#3D6FE0"), accent2 = cssRGB("--hb-accent2", "#8B5CF6");
  let W = 0, H = 0, cx = 0, cy = 0, raf = 0, stage = 0, bandAt = 0, burst = false, onDone = null, doneAt = 0;
  const nodes = [];
  for (let i = 0; i < NODE_COUNT; i++) {
    const ring = i < RING_N;
    nodes.push({ ring, a: ring ? (i / RING_N) * Math.PI * 2 : Math.random() * Math.PI * 2,
      rad: ring ? 0 : 0.1 + 0.9 * Math.sqrt(Math.random()), seed: Math.random() * 1000, born: ring ? -1 : null, ord: 0 });
  }
  const mesh = nodes.slice(RING_N).sort((p, q) => p.rad - q.rad);   // grows from the centre outwards
  mesh.forEach((n, k) => { n.ord = k; });
  let edges = [];

  function layout() {
    const r = canvas.getBoundingClientRect(), dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = r.width; H = r.height; cx = W / 2; cy = H * 0.46;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    for (const n of mesh) { n.hx = cx + Math.cos(n.a) * n.rad * W * 0.56; n.hy = cy + Math.sin(n.a) * n.rad * H * 0.56; }
    edges = [];
    for (let i = 0; i < mesh.length; i++) {   // each piece to its two nearest — enough to read as a mesh
      const d = mesh.map((m, j) => [j, (m.hx - mesh[i].hx) ** 2 + (m.hy - mesh[i].hy) ** 2]).sort((x, y) => x[1] - y[1]);
      for (const [j] of d.slice(1, 3)) if (i < j) edges.push([mesh[i], mesh[j]]);
    }
  }

  /** How many mesh pieces the current stage shows. */
  const target = () => Math.round(STAGE_REVEAL[stage] * mesh.length);

  function setStage(n) {
    n = Math.min(STAGE_READY - 1, n | 0);           // only finish() reaches the last stage
    if (n <= stage || burst) return;
    stage = n; bandAt = performance.now() / 1000;
  }

  function finish(cb) {
    if (burst) return;
    burst = true; stage = STAGE_READY; onDone = cb; bandAt = performance.now() / 1000;
    doneAt = performance.now() + BURST_MS;
  }

  function frame(nowMs) {
    const t = nowMs / 1000;
    ctx.clearRect(0, 0, W, H);
    const lim = target(), first = mesh.findIndex((n) => n.born === null), band = Math.max(1, lim - first);
    for (const n of mesh) {                        // the pieces this step owes appear, staggered over one band
      if (n.born !== null || n.ord >= lim) continue;
      n.born = bandAt + ((n.ord - first) / band) * (burst ? BURST_MS / 1000 - POP_S : BAND_S);
    }
    const spin = reduced ? 0 : (t / RING_PERIOD) * Math.PI * 2;
    const pos = (n) => {
      if (n.ring) return [cx + Math.cos(n.a + spin) * RING_R, cy + Math.sin(n.a + spin) * RING_R, 1];
      const k = n.born === null ? 0 : Math.max(0, Math.min(1, (t - n.born) / POP_S));
      const drift = reduced ? 0 : 5, e = burst ? easeOut(k) : 1;   // the burst flies out from the centre
      return [cx + (n.hx + Math.sin(t * 0.6 + n.seed) * drift - cx) * e,
              cy + (n.hy + Math.cos(t * 0.5 + n.seed) * drift - cy) * e, k];
    };
    ctx.lineWidth = 1;
    for (const [a, b] of edges) {
      const [ax, ay, ka] = pos(a), [bx, by, kb] = pos(b), k = Math.min(ka, kb);
      if (k <= 0) continue;
      ctx.strokeStyle = rgba(mix(accent, accent2, a.rad), 0.16 * k);
      ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke();
    }
    for (const n of nodes) {
      const [x, y, k] = pos(n);
      if (k <= 0) continue;
      const col = mix(accent, accent2, n.rad), glow = 0.5 + 0.5 * Math.sin(t * 1.7 + n.seed);
      const g = ctx.createRadialGradient(x, y, 0, x, y, 10 * k);
      g.addColorStop(0, rgba(col, (0.35 + 0.25 * glow) * k)); g.addColorStop(1, rgba(col, 0));
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, 10 * k, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = rgba([240, 244, 255], 0.9 * k);
      ctx.beginPath(); ctx.arc(x, y, (n.ring ? 2.6 : 1.8) * (0.4 + 0.6 * k), 0, Math.PI * 2); ctx.fill();
    }
    if (burst && nowMs >= doneAt && onDone) { const cb = onDone; onDone = null; cb(); }
    raf = requestAnimationFrame(frame);
  }

  const onResize = () => layout();
  layout();
  window.addEventListener("resize", onResize);
  raf = requestAnimationFrame(frame);
  return {
    setStage, finish,
    /** 0..1 — the share of the mesh the reached stage shows: what the progress bar reports. */
    shown: () => STAGE_REVEAL[stage],
    destroy() { cancelAnimationFrame(raf); window.removeEventListener("resize", onResize); },
  };
}
