// ============================================================================
// boot-anim.js — the ONE loader's growth: «Synaptic hive».
//
// The mesh is the original hive (restored 2026-11-12 from before V2-881): an organic elliptical disk of ~240 neurons
// joined to their three nearest, a shimmer travelling the synapses, spontaneous firings whose sparks cascade to the
// neighbours, a ripple when a neuron appears and a soft trail wash. V2-881 added the ring of eight dots turning in the
// centre — the same eight the HTML paints before any module — and that ring stays.
//
// THE BRAIN (operator, 2026-11-16, App Review recording): the mesh is a BRAIN seen from above — two hemispheres with
// the fissure between them along the long axis and a folded outline — and it BUILDS ITSELF FROM THE CENTRE OUTWARDS,
// slower: every neuron joins the brain through a synapse from an older one nearer the ring (`parentOf`), so what you
// watch is a tree of light growing out of the core, never sparks appearing anywhere. Portrait screens get a brain
// standing up, landscape one lying down, and it always fits inside the screen with its margin.
//
// THE GROWTH (operator, 2026-11-12): continuous and driven by TIME, not by the boot phases, at a steady organic
// cadence (`growthOrder`: a radial wavefront with a little jitter, so every side grows at once), never in batches. The growth slows towards a ceiling
// below the whole mesh (`GROW.CAP`): only `finish()` — called on `store.bootReady` — completes it, and then the rest
// develops very fast (`GROW.FINISH_S`) before the veil lifts. A real phase may pull the growth forward (`setStage`
// raises a floor it catches up to), always at a bounded rate so it never lands as a batch.
//
// Pure <canvas>, no deps; colours from the --hb-* tokens; honours prefers-reduced-motion (no spin, drift or sparks;
// the growth itself is the progress and stays).
// Contract: startBootAnim(canvas, { onProgress }) → { setStage(n), finish(onDone), shown(), destroy() }.
// ============================================================================

/** The growth schedule. Fractions are of the mesh beyond the ring; rates are fractions per second. */
export const GROW = { CAP: 0.92, TAU: 11, RAMP_S: 1.6, MAX_RATE: 0.15, CATCHUP: 1.2, FINISH_S: 0.5 };
/** A real stage's floor — 0 the ring (HTML), 1 /healthz, 2 the interface loaded, 3 voice, 4 memory, 5 reflex, 6 ready. */
export const STAGE_FLOOR = [0, 0.03, 0.06, 0.3, 0.5, 0.7, 1];
export const STAGE_READY = STAGE_FLOOR.length - 1;
export const BURST_MS = 380;      // the veil's fade once the growth is complete
const NODE_COUNT = 280;
const NEIGHBOURS = 3;             // edges per node (to its nearest N)
const RING_N = 8;                 // the dots of the first ring
const RING_R = 22;                // px; equals `.pb-ring` in core/shared-surfaces.css
const RING_PERIOD = 2.4;          // seconds per turn; equals the `pb-turn` animation
const APPEAR_S = 0.6;             // how long one neuron takes to light up (its synapse draws in over the same time)
// LIVING BRAIN: while we wait, the lit mesh fires spontaneously and the spark travels to the neighbours.
const IGNITE_RATE = 3.2, PULSE_DUR = 0.34, PULSE_FANOUT = 3, CASCADE_DECAY = 0.52, CASCADE_MIN = 0.12;
const MAX_PULSES = 90, FIRE_DECAY = 2.8;

/** One step of the growth: `p` (0..1 of the mesh shown) after `dt` seconds, `t` seconds since it started, with the
 *  floor the reached stage asks for. Pure — the test drives it frame by frame. */
export function growStep(p, dt, t, floor, finishing) {
  if (finishing) return Math.min(1, p + dt / GROW.FINISH_S);
  const ramp = Math.min(1, t / GROW.RAMP_S);
  const rate = Math.min(GROW.MAX_RATE,
    Math.max(ramp * (GROW.CAP - p) / GROW.TAU, (Math.min(floor, GROW.CAP) - p) * GROW.CATCHUP));
  return Math.min(GROW.CAP, p + Math.max(0, rate) * dt);
}

/** The order the neurons appear in: a wavefront from the centre outwards. Each point's depth is its distance from
 *  the centre measured against the brain's own outline (`edge(angle)`, 1 = the rim), plus a little jitter so the front
 *  is organic and every side grows at once. `pts` = [{x, y, rim}] (`rim` = that point's outline radius, px), `rnd` =
 *  a () → [0,1) source. Pure. */
export function growthOrder(pts, cx, cy, rnd = Math.random) {
  const key = pts.map((p, i) => [i, Math.hypot(p.x - cx, p.y - cy) / Math.max(1, p.rim || 1) + (rnd() - 0.5) * 0.12]);
  key.sort((a, b) => a[1] - b[1]);
  return key.map(([i]) => i);
}

/** Every neuron but the first joins the brain through ONE synapse from an OLDER neuron (the nearest one that appeared
 *  before it), so the growth reads as a tree out of the core. `order` from growthOrder. Returns [[parent, child]]. */
export function parentOf(pts, order) {
  const out = [];
  for (let k = 1; k < order.length; k++) {
    const c = order[k];
    let best = order[0], bd = Infinity;
    for (let q = Math.max(0, k - 120); q < k; q++) {           // the recent front: the nearest older is in it
      const o = order[q], d = (pts[o].x - pts[c].x) ** 2 + (pts[o].y - pts[c].y) ** 2;
      if (d < bd) { bd = d; best = o; }
    }
    out.push([best, c]);
  }
  return out;
}

/** The brain's outline at angle `a`, as a fraction of its radii: a folded rim (gyri), slightly fuller at the front. */
export function brainEdge(a) { return 1 + 0.05 * Math.sin(a * 7 + 0.6) + 0.035 * Math.sin(a * 13 + 2.1) + 0.04 * Math.cos(a); }

function toRGB(name, fallback) {
  const s = (getComputedStyle(document.documentElement).getPropertyValue(name) || "").trim() || fallback;
  let m = s.match(/^#([0-9a-f]{3})$/i);
  if (m) return [m[1][0], m[1][1], m[1][2]].map((c) => parseInt(c + c, 16));
  m = s.match(/^#([0-9a-f]{6})$/i);
  if (m) return [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16));
  m = s.match(/rgba?\(([^)]+)\)/i);
  return m ? m[1].split(",").slice(0, 3).map((n) => parseInt(n, 10)) : [120, 140, 170];
}
const rgba = ([r, g, b], a) => `rgba(${r | 0},${g | 0},${b | 0},${a})`;
const lerp = (a, b, t) => a + (b - a) * t;
const lerpRGB = (a, b, t) => [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)];

export function startBootAnim(canvas, { onProgress } = {}) {
  const ctx = canvas.getContext("2d");
  const reduced = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const accent = toRGB("--hb-accent", "#3D6FE0"), accent2 = toRGB("--hb-accent2", "#8B5CF6");
  const bg = toRGB("--hb-bg", "#0d1622");
  let W = 0, H = 0, cx = 0, cy = 0, span = 0, raf = 0, t0 = 0, lastT = 0, igniteAcc = 0;
  let p = 0, floor = STAGE_FLOOR[0], stage = 0, finishing = false, onDone = null, reported = -1;
  const nodes = [], pulses = [];
  let edges = [], adj = [];
  // Two hemispheres: a point too close to the fissure (the long axis' midline) is drawn again, except in the core
  // around the ring, where the two halves meet. Denser towards the rim, like a cortex.
  while (nodes.length < NODE_COUNT) {
    const a = Math.random() * Math.PI * 2, rad = 0.14 + 0.86 * Math.pow(Math.random(), 0.42);
    if (rad > 0.28 && Math.abs(Math.sin(a)) * rad < 0.085) continue;   // the fissure (rotated onto the long axis below)
    nodes.push({ a, rad, seed: Math.random() * 1000, hx: 0, hy: 0, x: 0, y: 0, ord: 0, act: 0, ripple: -1, fire: 0 });
  }
  let ordered = false, tree = [], trunk = new Set();

  function layout() {
    const r = canvas.getBoundingClientRect(), dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = r.width; H = r.height; cx = W / 2; cy = H * 0.46; span = Math.min(W, H) * 0.34;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    // The long axis follows the screen (a brain lying down on a desk, standing up on a phone) and both radii keep a
    // margin inside the screen — the old disk spilled past a 390 px phone's edges.
    const portrait = H > W * 1.15;
    const long = Math.min(span * 1.45, (portrait ? H * 0.34 : W * 0.42)), short = Math.min(long * 0.74, (portrait ? W : H) * 0.40);
    const [rx, ry] = portrait ? [short, long] : [long, short];
    for (const n of nodes) {
      // the fissure was cut at sin(a)≈0; on a standing brain it has to run vertically, so the angle turns a quarter
      const a = portrait ? n.a + Math.PI / 2 : n.a, e = brainEdge(n.a);
      n.hx = cx + Math.cos(a) * n.rad * e * rx; n.hy = cy + Math.sin(a) * n.rad * e * ry;
      n.rim = Math.hypot(Math.cos(a) * e * rx, Math.sin(a) * e * ry);
    }
    if (!ordered) {
      const pts = nodes.map((n) => ({ x: n.hx, y: n.hy, rim: n.rim }));
      const order = growthOrder(pts, cx, cy);
      order.forEach((idx, rank) => { nodes[idx].ord = rank; });
      tree = parentOf(pts, order);
      trunk = new Set(tree.map(([x, y]) => Math.min(x, y) * 4096 + Math.max(x, y)));
      ordered = true;
    }
    edges = [];
    for (let i = 0; i < nodes.length; i++) {
      const d = [];
      for (let j = 0; j < nodes.length; j++) if (j !== i) d.push([j, (nodes[i].hx - nodes[j].hx) ** 2 + (nodes[i].hy - nodes[j].hy) ** 2]);
      d.sort((a, b) => a[1] - b[1]);
      for (let k = 0; k < NEIGHBOURS; k++) if (d[k] && i < d[k][0]) edges.push([i, d[k][0]]);
    }
    const have = new Set(edges.map(([i, j]) => i * 4096 + j));     // the growth tree's synapses join the mesh
    for (const [a, b] of tree) { const [i, j] = a < b ? [a, b] : [b, a]; if (!have.has(i * 4096 + j)) { edges.push([i, j]); have.add(i * 4096 + j); } }
    adj = nodes.map(() => []);
    for (const [i, j] of edges) { adj[i].push(j); adj[j].push(i); }
  }

  // A neuron FIRES: flare, ripple, and sparks down a few of its LIT synapses.
  function ignite(idx, energy) {
    const n = nodes[idx];
    if (!n || n.act <= 0.05) return;
    n.fire = Math.min(1.5, n.fire + energy); n.ripple = 0;
    if (reduced || pulses.length >= MAX_PULSES) return;
    let count = 0;
    for (const j of adj[idx]) {
      if (count >= PULSE_FANOUT || pulses.length >= MAX_PULSES) break;
      if (nodes[j].act > 0.05 && Math.random() < 0.72) {
        pulses.push({ i: idx, j, t: 0, dur: PULSE_DUR * (0.8 + Math.random() * 0.5), energy }); count++;
      }
    }
  }

  function setStage(n) {
    n = Math.min(STAGE_READY - 1, n | 0);           // only finish() reaches the last stage
    if (n <= stage || finishing) return;
    stage = n; floor = STAGE_FLOOR[n];
  }

  function finish(cb) {
    if (finishing) return;
    finishing = true; stage = STAGE_READY; onDone = cb;
    // rAF stops in a background tab: the hand-over must not wait for the next visible frame.
    setTimeout(() => { if (onDone) { const f = onDone; onDone = null; f(); } }, GROW.FINISH_S * 1000 + 60);
  }

  function frame(now) {
    if (!t0) t0 = now;
    const t = (now - t0) / 1000, dt = Math.min(0.05, Math.max(0, t - lastT));
    lastT = t;
    p = growStep(p, dt, t, floor, finishing);
    const pct = Math.round(p * 100);
    if (pct !== reported) { reported = pct; if (onProgress) onProgress(p); }
    const shown = p * NODE_COUNT, appear = finishing ? 0.15 : APPEAR_S;

    if (!reduced && !finishing) {
      igniteAcc += dt * IGNITE_RATE;
      if (igniteAcc >= 1) {
        const lit = [];
        for (let i = 0; i < nodes.length; i++) if (nodes[i].act > 0.4) lit.push(i);
        while (igniteAcc >= 1) { igniteAcc -= 1; if (lit.length) ignite(lit[(Math.random() * lit.length) | 0], 0.9 + Math.random() * 0.5); }
      }
    }

    ctx.globalCompositeOperation = "source-over";   // the trail wash: «liquid light» instead of a hard clear
    ctx.fillStyle = rgba(bg, reduced ? 1 : 0.30);
    ctx.fillRect(0, 0, W, H);

    const drift = reduced ? 0 : 6;
    for (const n of nodes) {
      if (n.act === 0 && n.ord < shown) { n.act = 0.001; n.ripple = 0; }   // this neuron's turn
      if (n.act > 0 && n.act < 1) n.act = Math.min(1, n.act + dt / appear);
      if (n.fire > 0) n.fire = Math.max(0, n.fire - dt * FIRE_DECAY);
      if (n.ripple >= 0) { n.ripple += dt * 2.4; if (n.ripple > 1) n.ripple = -1; }
      n.x = n.hx + Math.sin(t * 0.6 + n.seed) * drift + Math.cos(t * 0.37 + n.seed * 1.7) * drift * 0.6;
      n.y = n.hy + Math.cos(t * 0.5 + n.seed * 1.3) * drift + Math.sin(t * 0.41 + n.seed) * drift * 0.6;
    }

    // synapses — drawn in from the older neuron towards the newer as the newer lights up; a shimmer runs the mesh
    ctx.lineWidth = 1;
    for (const [i, j] of edges) {
      const a0 = nodes[i], b0 = nodes[j], [a, b] = a0.ord < b0.ord ? [a0, b0] : [b0, a0];
      if (a.act <= 0.02 || b.act <= 0.02) continue;
      const k = b.act, ex = lerp(a.x, b.x, k), ey = lerp(a.y, b.y, k);
      const col = lerpRGB(accent, accent2, 0.5 + 0.5 * Math.sin(t * 1.6 - (i + j) * 0.25));
      ctx.strokeStyle = rgba(col, (trunk.has(i * 4096 + j) ? 0.24 : 0.10) * Math.min(a.act, k));   // the growth tree reads
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(ex, ey); ctx.stroke();
      if (!reduced && k > 0.6) {
        const tp = (t * 0.4 + (i * 0.13 + j * 0.07)) % 1;
        ctx.fillStyle = rgba(col, 0.28 * k);
        ctx.beginPath(); ctx.arc(lerp(a.x, b.x, tp), lerp(a.y, b.y, tp), 1.2, 0, Math.PI * 2); ctx.fill();
      }
    }

    // synapse sparks — on arrival they re-fire the neighbour with decayed energy (a cascade that fades)
    if (pulses.length) {
      ctx.globalCompositeOperation = "lighter";
      for (let q = pulses.length - 1; q >= 0; q--) {
        const pu = pulses[q], a = nodes[pu.i], b = nodes[pu.j];
        pu.t += dt / pu.dur;
        const arrived = pu.t >= 1, tp = arrived ? 1 : pu.t, px = lerp(a.x, b.x, tp), py = lerp(a.y, b.y, tp);
        const col = lerpRGB(accent, accent2, 0.5 + 0.5 * Math.sin(t * 1.6 - (pu.i + pu.j) * 0.25));
        const g = ctx.createRadialGradient(px, py, 0, px, py, 7 * pu.energy);
        g.addColorStop(0, rgba(col, 0.9 * pu.energy)); g.addColorStop(1, rgba(col, 0));
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(px, py, 7 * pu.energy, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = rgba([236, 242, 255], 0.9 * pu.energy);
        ctx.beginPath(); ctx.arc(px, py, 2.2 * pu.energy, 0, Math.PI * 2); ctx.fill();
        if (arrived) {
          pulses.splice(q, 1);
          if (!finishing && pu.energy * CASCADE_DECAY > CASCADE_MIN) ignite(pu.j, pu.energy * CASCADE_DECAY);
        }
      }
      ctx.globalCompositeOperation = "source-over";
    }

    // neurons — glow + core, the colour sweeping from the centre outwards; the flare when one fires; a ripple ring when it appears
    for (const n of nodes) {
      if (n.act <= 0) continue;
      const fl = Math.min(1, n.fire), col = lerpRGB(accent, accent2, (n.rad - 0.14) / 0.86), gr = 9 * n.act + fl * 13;
      const g = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, gr);
      g.addColorStop(0, rgba(lerpRGB(col, [255, 255, 255], fl * 0.6), 0.5 * n.act + fl * 0.55)); g.addColorStop(1, rgba(col, 0));
      if (fl > 0.02) ctx.globalCompositeOperation = "lighter";
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(n.x, n.y, gr, 0, Math.PI * 2); ctx.fill();
      ctx.globalCompositeOperation = "source-over";
      ctx.fillStyle = rgba([245, 248, 255], Math.min(1, 0.85 * n.act + fl * 0.6));
      ctx.beginPath(); ctx.arc(n.x, n.y, 1.8 + n.act + fl * 2.4, 0, Math.PI * 2); ctx.fill();
      if (n.ripple >= 0) {
        ctx.strokeStyle = rgba(col, 0.4 * (1 - n.ripple)); ctx.lineWidth = 1.2;
        ctx.beginPath(); ctx.arc(n.x, n.y, 4 + n.ripple * 22, 0, Math.PI * 2); ctx.stroke();
      }
    }

    // the ring in the centre, turning — the same eight dots the HTML painted first
    const spin = reduced ? 0 : (t / RING_PERIOD) * Math.PI * 2;
    for (let i = 0; i < RING_N; i++) {
      const a = (i / RING_N) * Math.PI * 2 + spin, x = cx + Math.cos(a) * RING_R, y = cy + Math.sin(a) * RING_R;
      const g = ctx.createRadialGradient(x, y, 0, x, y, 9);
      g.addColorStop(0, rgba(accent, 0.55)); g.addColorStop(1, rgba(accent, 0));
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, 9, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "rgba(240,244,255,0.95)"; ctx.beginPath(); ctx.arc(x, y, 2.6, 0, Math.PI * 2); ctx.fill();
    }

    if (finishing && p >= 1 && onDone) { const f = onDone; onDone = null; f(); }
    raf = requestAnimationFrame(frame);
  }

  const onResize = () => layout();
  layout();
  window.addEventListener("resize", onResize);
  raf = requestAnimationFrame(frame);
  return {
    setStage, finish,
    /** 0..1 — the share of the mesh grown so far: what the progress bar reports. */
    shown: () => p,
    destroy() { cancelAnimationFrame(raf); window.removeEventListener("resize", onResize); },
  };
}
