// mouth.js — a richer SPEAKING mouth (V2-928), PARKED: built 2026-11-18 and taken back out the same day — the operator
// preferred the simpler, less realistic mouth, and the richer one also made the ~52 ms lag of the lip-sync model (it hears
// a sound before it names it) easier to see. NOTHING imports this file today. To wire it back:
//   1. rig.js: replace the «mouth from visemes» block with `const mt = mouthFrom(v), open = mt.open;` and ease every
//      channel of MOUTH_EASE into the rig state; add the five new channels (upper lower bite tip funnel) to the frame;
//   2. rig.js geometry(): use `articulatedMouth(r, MO, n)` (below) as `mouth()`;
//   3. face.js drawLook(): after the style, `if (r.open > 0.04 && showsInside(look)) drawMouthInside(ctx, G);`
// The test that keeps it alive (node 4.575) drives these functions directly and pins that nothing wires them.
//
// What it does: the lip-sync model gives the weights of the 15 Oculus visemes; instead of folding them into four
// numbers, each sound is a RECIPE over nine channels — «m» seals the lips, «f» tucks the lower lip under the upper
// teeth, «t d n l» lift the tongue tip, «th» puts it between the teeth, «o u» round the lips, «i e» stretch them — and
// the human-like looks show teeth and a tongue inside the opening. At rest every channel is 0: the old mouth exactly.

/** The channels: open (jaw) · wide (−1 pursed … 1 stretched) · round (lips rounded) · press (lips sealed) · upper (the
 *  upper lip lifts: the upper teeth show) · lower (the lower lip drops: the lower teeth show) · bite (the lower lip under
 *  the upper teeth) · tip (the tongue tip up at the teeth; 1 = between them) · funnel (lips pushed out, squared). */
export const CHANNELS = ["open", "wide", "round", "press", "upper", "lower", "bite", "tip", "funnel"];

/** One recipe per viseme (Oculus set). Spanish and English vowels: a → aa, e → E, i → I, o → O, u → U. */
export const MOUTH_SHAPES = {
  PP: { press: 1, wide: -0.05 },                                                    // p b m — sealed
  FF: { open: 0.22, bite: 1, upper: 0.5, wide: 0.1 },                                 // f v — lower lip under the teeth
  TH: { open: 0.22, tip: 1, wide: 0.2, upper: 0.35, lower: 0.3 },                   // th (θ ð, Spanish z/c) — tongue out
  DD: { open: 0.3, tip: 0.7, wide: 0.25, upper: 0.3, lower: 0.3 },                  // t d — tip at the teeth
  kk: { open: 0.38, wide: 0.2, upper: 0.2, lower: 0.35 },                           // k g (h) — open, tongue back
  CH: { open: 0.3, round: 0.4, funnel: 1, upper: 0.55, lower: 0.5, wide: -0.1 },    // ch sh j — lips out, square
  SS: { open: 0.1, wide: 0.6, upper: 0.6, lower: 0.5 },                             // s z — teeth together, showing
  nn: { open: 0.25, tip: 0.6, wide: 0.2, upper: 0.2, lower: 0.2 },                  // n l — tip up
  RR: { open: 0.25, round: 0.55, funnel: 0.5, wide: -0.2 },                         // r
  aa: { open: 0.9, wide: 0.3, upper: 0.25, lower: 0.65 },                           // a
  E:  { open: 0.5, wide: 0.7, upper: 0.45, lower: 0.45 },                           // e
  I:  { open: 0.3, wide: 0.95, upper: 0.55, lower: 0.35 },                          // i
  O:  { open: 0.6, round: 0.8, wide: -0.3, lower: 0.2 },                           // o
  U:  { open: 0.32, round: 1, wide: -0.4, funnel: 0.4 },                            // u
};
// The coarticulation tops a held sound out at this weight (0.9 for a closure): divided out, a held vowel reaches its
// whole recipe instead of three quarters of it.
const LEVEL = 0.78;
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));

/** The viseme weights of one frame → the nine channels (a weighted sum of the recipes). */
export function mouthFrom(v = {}) {
  const out = Object.fromEntries(CHANNELS.map((c) => [c, 0]));
  for (const k in v) {
    const w = v[k], shape = MOUTH_SHAPES[k];
    if (!shape || !(w > 0)) continue;
    for (const c in shape) out[c] += w * shape[c];
  }
  for (const c of CHANNELS) out[c] = c === "wide" ? clamp(out[c] / LEVEL, -1, 1) : clamp(out[c] / LEVEL, 0, 1);
  return out;
}

/** How fast each channel follows (ms): a closure snaps, the jaw is quick, the lips' shape a little slower. */
export const MOUTH_EASE = { open: 28, wide: 40, round: 40, press: 16, upper: 35, lower: 35, bite: 22, tip: 30, funnel: 45 };

/** The looks that show the inside of the mouth: the classic Porcelain, and the parametric mouths that are a hole. */
export const INSIDE_STYLES = new Set(["porcelain"]);
export const INSIDE_SPEC_MOUTHS = new Set(["filled", "lips", "o"]);
export function showsInside(look) {
  if (look && look.spec) return INSIDE_SPEC_MOUTHS.has(look.spec.mouth && look.spec.mouth.type);
  return !!(look && look.style && INSIDE_STYLES.has(look.style.id));
}

export const INSIDE_COLOURS = { teeth: "#f4f1e8", tongue: "#c65d6f", tongueDark: "#9b4152" };

/** Teeth and tongue inside the opening, clipped to it (drawn over the style's dark mouth). Nothing when it is shut. */
export function drawMouthInside(ctx, G, colours = INSIDE_COLOURS) {
  const r = G.r, m = G.mouth();
  if (m.h < 0.02) return;
  const lift = 0.04, P = (uv) => G.P(uv, lift);
  const line = (pts, close) => { ctx.beginPath(); pts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y))); if (close) ctx.closePath(); };
  const up = r.upper || 0, lo = r.lower || 0, bite = r.bite || 0, tip = r.tip || 0;
  ctx.save();
  line(m.upper.concat(m.lower.slice().reverse()).map(P), true); ctx.clip();
  const n = m.upper.length, a = Math.floor(n * 0.1), b = Math.ceil(n * 0.9);
  const bottom = Math.min(...m.lower.map((p) => p[1]));
  // the tongue lies low in the mouth; its tip rises to the teeth (t d n l) and, for «th», pushes between them
  const tongueY = bottom + m.h * (0.15 + 0.45 * tip), tc = P([0, tongueY]), tr = P([m.mw * 0.55, tongueY]);
  ctx.beginPath(); ctx.ellipse(tc.x, tc.y, Math.abs(tr.x - tc.x), Math.max(1, m.h * (0.3 + 0.2 * tip) * tc.s), G.r.roll, 0, Math.PI * 2);
  ctx.fillStyle = colours.tongue; ctx.fill();
  // the upper teeth hang from the upper lip — more of them as it lifts, and over the lower lip for «f v»
  const th = 0.026 + 0.03 * up + 0.04 * bite;
  const upperTeeth = m.upper.slice(a, b);
  line(upperTeeth.map(P).concat(upperTeeth.slice().reverse().map(([x, y]) => P([x, y - th]))), true);
  ctx.fillStyle = colours.teeth; ctx.fill();
  // the lower teeth show when the lower lip drops
  if (lo > 0.15) {
    const lowerTeeth = m.lower.slice(a + 2, b - 2), lh = 0.012 + 0.022 * lo;
    line(lowerTeeth.map(P).concat(lowerTeeth.slice().reverse().map(([x, y]) => P([x, y + lh]))), true);
    ctx.globalAlpha *= Math.min(1, (lo - 0.15) * 3); ctx.fillStyle = colours.teeth; ctx.fill();
  }
  ctx.restore();
  // «th»: the tip between the teeth, drawn over them (still inside the opening's outline)
  if (tip > 0.85 && m.h > 0.03) {
    const topY = Math.max(...m.upper.slice(a, b).map((p) => p[1])) - th, c = P([0, topY]);
    ctx.beginPath(); ctx.ellipse(c.x, c.y, m.mw * 0.28 * c.s, Math.max(1, 0.018 * c.s), G.r.roll, 0, Math.PI * 2);
    ctx.fillStyle = colours.tongue; ctx.fill();
  }
}

/** The mouth opening with the nine channels (what rig.js geometry().mouth() would become). `MO` = the shape's mouth. */
export function articulatedMouth(r, MO = { y: -0.42, k: 1 }, n = 24) {
  const up = r.upper || 0, lo = r.lower || 0, bite = r.bite || 0, fun = r.funnel || 0, wide = Math.max(0, r.wide);
  const my = MO.y + 0.012 * bite;
  const mw = 0.2 * MO.k * (1 + 0.35 * r.wide - 0.4 * r.round - 0.18 * fun + 0.15 * Math.max(0, r.smile)) * (1 - 0.06 * r.press);
  const h = (0.012 + 0.21 * r.open) * (r.press > 0 ? 1 - r.press * 0.97 : 1) * (1 - 0.5 * bite) * Math.sqrt(MO.k);
  const c = r.smile * 0.07 * MO.k;
  const upper = [], lower = [], hu = 0.25 + 0.15 * up, hl = 0.75 + 0.15 * lo;
  for (let i = 0; i <= n; i++) {
    const k = (i / n) * 2 - 1, body = 1 - k * k;
    const roundBody = Math.sqrt(Math.max(0, body));
    let prof = body * (1 - r.round) + roundBody * r.round;
    if (wide > 0) prof = prof ** (1 - 0.45 * wide);                           // stretched lips: a flatter opening
    if (fun > 0) prof = prof * (1 - 0.6 * fun) + Math.max(0, body) ** 0.35 * 0.6 * fun;   // pushed out: squared
    upper.push([k * mw, my + c * k * k + hu * h * prof]);
    lower.push([k * mw, my + c * k * k - hl * h * prof - c * 0.4 * body]);
  }
  return { upper, lower, my, mw, h };
}
