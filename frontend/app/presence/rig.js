// rig.js — ONE face rig shared by every style (V2-928).
// Input each frame: the lip-sync visemes (from the vendored model), the mood and any running gesture.
// Output: a small set of numbers (mouth open/wide/round/press, eyes, brows, head pose…) plus a geometry helper
// that projects face points from a 3D head onto the canvas. Every style draws from the same rig, so lip sync,
// blinking and gestures behave identically across styles and only the look changes.

import { createLife } from "./life.js?v=1";
import { mouthFrom, MOUTH_EASE } from "./mouth.js?v=1";

const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const ease = (cur, target, dt, ms) => cur + (target - cur) * (1 - Math.exp(-dt / ms));
const drift = (t, s) => Math.sin(t * 0.31 + s) * 0.6 + Math.sin(t * 0.17 + s * 2.3) * 0.3 + Math.sin(t * 0.73 + s * 0.7) * 0.1;
const bell = (p) => Math.sin(Math.PI * clamp(p));
// up quickly, held, down quickly (a pose that has to be SEEN, like a tongue out)
const plateau = (p, a = 0.2, b = 0.25) => (p < a ? Math.sin((Math.PI / 2) * clamp(p / a)) : p > 1 - b ? Math.sin((Math.PI / 2) * clamp((1 - p) / b)) : 1);

// Gestures: duration (s) + what they add to the rig at progress p (0..1).
const GESTURES = {
  nod:      { dur: 1.1, fx: (p, r) => { r.pitch += 0.16 * Math.sin(p * Math.PI * 4) * bell(p); } },
  shake:    { dur: 1.2, fx: (p, r) => { r.yaw += 0.28 * Math.sin(p * Math.PI * 4) * bell(p); } },
  tilt:     { dur: 1.8, fx: (p, r) => { r.roll += 0.2 * bell(p); r.smile += 0.3 * bell(p); } },
  smile:    { dur: 2.2, fx: (p, r) => { r.smile += 0.9 * bell(p); r.squint += 0.35 * bell(p); r.brow += 0.15 * bell(p); } },
  laugh:    { dur: 2.0, fx: (p, r, t) => { const b = bell(p); r.smile += b; r.squint += 0.7 * b; r.open = Math.max(r.open, b * (0.35 + 0.2 * Math.sin(t * 22))); r.pitch -= 0.06 * b; } },
  surprise: { dur: 1.6, fx: (p, r) => { const b = bell(p); r.brow += 0.9 * b; r.eyeScale += 0.35 * b; r.open = Math.max(r.open, 0.45 * b); r.round = Math.max(r.round, 0.8 * b); r.pitch -= 0.05 * b; } },
  wink:     { dur: 0.9, fx: (p, r) => { r.blinkR = Math.max(r.blinkR, bell(p)); r.smile += 0.5 * bell(p); r.roll += 0.06 * bell(p); } },
  winkL:    { dur: 0.9, fx: (p, r) => { r.blinkL = Math.max(r.blinkL, bell(p)); r.smile += 0.5 * bell(p); r.roll -= 0.06 * bell(p); } },
  // «the face answers you» (T12, humanity/): what it may give back besides the gestures above
  tongue:   { dur: 1.7, fx: (p, r) => { const b = plateau(p); r.tongue = Math.max(r.tongue, b); r.open = Math.max(r.open, 0.22 * b); r.wide += 0.2 * b; r.squint += 0.3 * b; r.roll += 0.05 * b; } },
  giggle:   { dur: 1.2, fx: (p, r, t) => { const b = bell(p); r.smile += 0.85 * b; r.squint += 0.55 * b; r.open = Math.max(r.open, b * (0.1 + 0.08 * Math.sin(t * 26))); r.roll += 0.05 * b; } },
  yawn:     { dur: 2.8, fx: (p, r) => { const b = plateau(p, 0.35, 0.3); r.open = Math.max(r.open, 0.85 * b); r.round = Math.max(r.round, 0.35 * b); r.blinkL = Math.max(r.blinkL, 0.7 * b); r.blinkR = Math.max(r.blinkR, 0.7 * b); r.pitch -= 0.1 * b; r.brow += 0.25 * b; } },
  sigh:     { dur: 1.9, fx: (p, r) => { const b = bell(p); r.blinkL = Math.max(r.blinkL, 0.5 * b); r.blinkR = Math.max(r.blinkR, 0.5 * b); r.pitch += 0.07 * b; r.smile -= 0.25 * b; r.open = Math.max(r.open, 0.08 * b); r.round = Math.max(r.round, 0.4 * b); } },
  brows:    { dur: 0.75, fx: (p, r) => { const b = bell(p); r.brow += 0.85 * b; r.eyeScale += 0.1 * b; } },
  look:     { dur: 3.2, fx: (p, r) => { const g = Math.sin(p * Math.PI * 2) * bell(p * 1.0); r.gazeX += 0.9 * g; r.yaw += 0.35 * g; } },
  sad:      { dur: 2.2, fx: (p, r) => { const b = bell(p); r.smile -= 0.8 * b; r.browIn += 0.8 * b; r.pitch += 0.08 * b; r.gazeY -= 0.4 * b; } },
};
export const GESTURE_NAMES = Object.keys(GESTURES);
// «Look at me» gets a GAZE in radians (look.js): the head takes this share of it, never past LOOK_HEAD_MAX, and the
// eyes the rest — an eye at full travel (gazeX = ±1) looks LOOK_EYE_RAD aside.
export const LOOK_HEAD = 0.3, LOOK_HEAD_MAX = 0.08, LOOK_EYE_RAD = 0.35;

const MOOD = {
  idle:      { lid: 0.42, smile: 0.12, brow: 0.0, glow: 0.45 },
  listening: { lid: 0.0,  smile: 0.32, brow: 0.12, glow: 0.85 },
  thinking:  { lid: 0.12, smile: 0.0,  brow: 0.25, glow: 1.0 },
};

export function createRig(rnd = Math.random) {
  const life = createLife(rnd);
  const rand = (a, b) => a + rnd() * (b - a);       // blinks and glances draw from the same source (seeded in tests)
  const s = {
    t: 0, mood: "listening", gestures: [],
    open: 0, wide: 0, round: 0, press: 0, upper: 0, lower: 0, bite: 0, tip: 0, funnel: 0, energy: 0,
    smile: MOOD.listening.smile, lid: 0, brow: 0, glow: 0.8, think: 0,
    blink: 0, blinkAt: -1, nextBlink: 1.5,
    gaze: { x: 0, y: 0 }, gazeTo: { x: 0, y: 0 }, nextSaccade: 1,
    look: null, lookW: 0, lookX: 0, lookY: 0,        // «look at me» (T10): where the person is, from look.js
  };

  function update(dtMs, frame) {
    const dt = dtMs;
    s.t += dt / 1000;
    const t = s.t;
    const v = frame.visemes || {};
    const speaking = frame.mode === "speaking";
    const m = MOOD[s.mood] || MOOD.listening;

    // ---- mouth from visemes (Oculus set): each sound its own recipe over nine channels (mouth.js) ----
    const mt = mouthFrom(v), open = mt.open;
    for (const c in MOUTH_EASE) s[c] = ease(s[c], mt[c], dt, MOUTH_EASE[c]);
    s.energy = ease(s.energy, speaking ? clamp(open * 1.2 + 0.3) : 0, dt, 110);
    s.think = ease(s.think, s.mood === "thinking" && !speaking ? 1 : 0, dt, 500);
    s.smile = ease(s.smile, speaking ? 0.18 : m.smile, dt, 400);
    s.lid = ease(s.lid, speaking ? 0 : m.lid, dt, 500);
    s.brow = ease(s.brow, (speaking ? 0.08 : m.brow) + s.energy * 0.12, dt, 250);
    s.glow = ease(s.glow, speaking ? 1 : m.glow, dt, 400);

    // ---- blinks ----
    if (t >= s.nextBlink) { s.blinkAt = t; s.nextBlink = t + rand(s.mood === "idle" ? 3 : 2, s.mood === "idle" ? 7 : 5.5); }
    const bp = (t - s.blinkAt) / 0.16;
    s.blink = bp >= 1 || bp < 0 ? 0 : bp < 0.4 ? bp / 0.4 : 1 - (bp - 0.4) / 0.6;

    // ---- saccades ----
    if (t >= s.nextSaccade) {
      const r = speaking ? 0.25 : 0.45;
      s.gazeTo = { x: rand(-r, r), y: rand(-r * 0.6, r * 0.6) };
      s.nextSaccade = t + rand(speaking ? 1.2 : 0.9, speaking ? 3.5 : 3);
    }
    const gx = s.gazeTo.x * (1 - s.think) - 0.6 * s.think, gy = s.gazeTo.y * (1 - s.think) + 0.6 * s.think;
    s.gaze.x = ease(s.gaze.x, gx, dt, 50); s.gaze.y = ease(s.gaze.y, gy, dt, 50);

    // ---- the rig for this frame ----
    const slow = s.mood === "idle" ? 0.6 : 1;
    const r = {
      t, mood: s.mood, speaking, energy: s.energy, glow: s.glow, think: s.think,
      open: s.open, wide: s.wide, round: s.round, press: s.press,
      upper: s.upper, lower: s.lower, bite: s.bite, tip: s.tip, funnel: s.funnel,
      smile: s.smile, squint: 0, eyeScale: 1, brow: s.brow, browIn: 0, tongue: 0,
      blinkL: Math.max(s.blink, s.lid), blinkR: Math.max(s.blink, s.lid),
      gazeX: s.gaze.x, gazeY: s.gaze.y,
      yaw: drift(t * slow, 5) * 0.09 + s.think * 0.14,
      pitch: drift(t * slow, 2) * 0.05 + s.energy * 0.04 * Math.sin(t * 7.3) - s.think * 0.06,
      roll: drift(t * slow, 8) * 0.035 + s.think * 0.07,
      breathe: Math.sin(t * Math.PI * 2 / (s.mood === "idle" ? 5.2 : 4.2)),
    };
    life.apply(r, { t, dt, speaking, mood: s.mood, open, hearing: !!frame.hearing, gesture: (n) => s.gestures.push({ name: n, start: t }) });
    lookAt(r, dt);
    s.gestures = s.gestures.filter((gst) => t - gst.start < GESTURES[gst.name].dur);
    for (const gst of s.gestures) GESTURES[gst.name].fx((t - gst.start) / GESTURES[gst.name].dur, r, t);
    r.smile = clamp(r.smile, -1, 1.2); r.squint = clamp(r.squint);
    r.blinkL = clamp(Math.max(r.blinkL, r.squint * 0.45)); r.blinkR = clamp(Math.max(r.blinkR, r.squint * 0.45));
    if (r.eyeScale > 1) { r.blinkL *= 2 - r.eyeScale; r.blinkR *= 2 - r.eyeScale; }
    return r;
  }

  // «Look at me» (V2-928 T10): the head and the eyes turn toward the person, eased like a real neck, keeping a share
  // of the idle life on top so a face that follows someone still breathes, glances and nods. The weight fades in and
  // out, so losing the person hands the head back to the idle life without a jump.
  function lookAt(r, dt) {
    const L = s.look;
    s.lookW = ease(s.lookW, L ? clamp(L.w) : 0, dt, 380);
    if (L) { s.lookX = ease(s.lookX, clamp(L.x, -0.5, 0.5), dt, 240); s.lookY = ease(s.lookY, clamp(L.y, -0.5, 0.5), dt, 300); }
    const w = s.lookW;
    if (w < 0.001) return;
    const keep = 1 - 0.65 * w, keepEye = 1 - 0.7 * w;
    const hx = clamp(s.lookX * LOOK_HEAD, -LOOK_HEAD_MAX, LOOK_HEAD_MAX), hy = clamp(s.lookY * LOOK_HEAD, -LOOK_HEAD_MAX, LOOK_HEAD_MAX);
    r.yaw = r.yaw * keep + w * hx;
    r.pitch = r.pitch * keep - w * hy;                               // pitch < 0 lifts the face
    r.gazeX = r.gazeX * keepEye + w * clamp((s.lookX - hx) / LOOK_EYE_RAD, -1, 1);   // the eyes take the rest of the gaze
    r.gazeY = r.gazeY * keepEye + w * clamp((s.lookY - hy) / LOOK_EYE_RAD, -1, 1);
  }

  return {
    update,
    /** Where the person is (`{x, y, w}`, look.js) or null for nobody: the face turns to them. */
    setLook(target) { s.look = target && Number.isFinite(target.x) && Number.isFinite(target.y) ? target : null; },
    get lookWeight() { return s.lookW; },
    setMood(m) { if (MOOD[m]) s.mood = m; },
    gesture(name) { if (GESTURES[name]) s.gestures.push({ name, start: s.t }); },
    get mood() { return s.mood; },
  };
}

// ---------------------------------------------------------------------------------------------------------------
// Geometry: a head ellipsoid, rotated by the rig's pose and projected with a light perspective.
// Face coordinates (u, v): u right, v up; the face spans roughly [-1, 1].
// ---------------------------------------------------------------------------------------------------------------
export const HEAD = { x: 1, y: 1.15, z: 0.95 };

// `shape` (optional) re-proportions the face for the parametric avatars; without it every number is the original
// one, so the classic styles draw exactly as before.
export const DEFAULT_SHAPE = { head: HEAD, eye: { x: 0.38, y: 0.1, w: 0.2, h: 0.13, k: 1 }, mouth: { y: -0.42, k: 1 } };
export function geometry(r, cx, cy, R, shape = DEFAULT_SHAPE) {
  const HD = shape.head, EYE = shape.eye, MO = shape.mouth;
  const cyw = Math.cos(r.yaw), syw = Math.sin(r.yaw), cp = Math.cos(r.pitch), sp = Math.sin(r.pitch);
  const cr = Math.cos(r.roll), sr = Math.sin(r.roll), f = 5;
  const breathe = 1 + r.breathe * 0.006;
  function proj(x, y, z) {
    // roll (z), pitch (x), yaw (y)
    let X = x * cr - y * sr, Y = x * sr + y * cr, Z = z;
    let Y2 = Y * cp - Z * sp, Z2 = Y * sp + Z * cp; Y = Y2; Z = Z2;
    let X2 = X * cyw + Z * syw; Z2 = -X * syw + Z * cyw; X = X2; Z = Z2;
    const s = (f / (f - Z)) * breathe;
    return { x: cx + X * R * s, y: cy - Y * R * s + r.breathe * R * 0.004, z: Z, s: s * R };
  }
  function surfZ(u, v) {
    const q = 1 - (u / HD.x) ** 2 - (v / HD.y) ** 2;
    return HD.z * Math.sqrt(Math.max(q, 0));
  }
  const pt = (u, v, lift = 0.02) => proj(u, v, surfZ(u, v) + lift);

  // ---- features in face coordinates ----
  function eye(side) {                               // side: -1 left, +1 right (viewer's)
    const blink = side < 0 ? r.blinkL : r.blinkR;
    const open = clamp(1 - blink) * r.eyeScale;
    const ex = side * EYE.x, ey = EYE.y + r.brow * 0.012;
    const w = EYE.w * (1 + (r.eyeScale - 1) * 0.3), h = EYE.h * open;
    const gx = r.gazeX * 0.07 * EYE.k, gy = r.gazeY * 0.05 * EYE.k;
    const outline = [];
    for (let i = 0; i <= 24; i++) {                   // almond (the logo's eye): two quadratic lids
      const a = (i / 24) * Math.PI * 2;
      const u = Math.cos(a), sgn = Math.sin(a) >= 0 ? 1 : -1;
      const lidH = sgn > 0 ? h * (1 - r.squint * 0.2) : h * (1 - r.squint * 0.6);
      outline.push([ex + u * w, ey + sgn * lidH * (1 - u * u)]);
    }
    return {
      c: [ex, ey], open, w, h, outline,
      iris: [ex + gx, ey + gy], irisR: 0.085 * r.eyeScale * EYE.k, coreR: 0.045 * r.eyeScale * EYE.k, k: EYE.k,
    };
  }
  function brow(side) {
    const by = EYE.y + 0.22 * Math.max(0.8, EYE.k) + r.brow * 0.09, bx = side * EYE.x, bw = 0.34 * Math.max(0.8, EYE.k);
    const pts = [];
    for (let i = 0; i <= 10; i++) {
      const k = i / 10 - 0.5;                        // inner → outer
      const inner = side < 0 ? 0.5 - k : 0.5 + k;   // 1 at the inner end
      pts.push([bx + k * bw, by + (0.25 - k * k) * 0.08 + r.browIn * 0.07 * inner - r.think * 0.03 * (side < 0 ? 1 : -1)]);
    }
    return pts;
  }
  // The opening of the mouth (mouth.js says what each channel is). With every speech channel at 0 it is exactly the
  // mouth it always was; a sealed «m» closes it, «f» leaves a slit under the teeth, «i e» flatten it wide, «sh» squares it.
  function mouth(n = 24) {
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
  const P = (uv, lift) => pt(uv[0], uv[1], lift);
  return { proj, pt, P, eye, brow, mouth, surfZ, R, cx, cy, r, shape, with: (x, y, rr) => geometry(r, x, y, rr, shape) };
}

// Fibonacci points on a unit sphere (cached), for the point-cloud styles.
const _fib = new Map();
export function fib(n) {
  if (_fib.has(n)) return _fib.get(n);
  const out = [], ga = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i++) {
    const y = 1 - (i / (n - 1)) * 2, rad = Math.sqrt(1 - y * y), th = ga * i;
    out.push([Math.cos(th) * rad, y, Math.sin(th) * rad, Math.random()]);
  }
  _fib.set(n, out);
  return out;
}
