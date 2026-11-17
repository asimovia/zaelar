// rig.js — ONE face rig shared by every style (V2-928).
// Input each frame: the lip-sync visemes (from the vendored model), the mood and any running gesture.
// Output: a small set of numbers (mouth open/wide/round/press, eyes, brows, head pose…) plus a geometry helper
// that projects face points from a 3D head onto the canvas. Every style draws from the same rig, so lip sync,
// blinking and gestures behave identically across styles and only the look changes.

import { createLife } from "./life.js?v=1";

const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const rand = (a, b) => a + Math.random() * (b - a);
const ease = (cur, target, dt, ms) => cur + (target - cur) * (1 - Math.exp(-dt / ms));
const drift = (t, s) => Math.sin(t * 0.31 + s) * 0.6 + Math.sin(t * 0.17 + s * 2.3) * 0.3 + Math.sin(t * 0.73 + s * 0.7) * 0.1;
const bell = (p) => Math.sin(Math.PI * clamp(p));

// Gestures: duration (s) + what they add to the rig at progress p (0..1).
const GESTURES = {
  nod:      { dur: 1.1, fx: (p, r) => { r.pitch += 0.16 * Math.sin(p * Math.PI * 4) * bell(p); } },
  shake:    { dur: 1.2, fx: (p, r) => { r.yaw += 0.28 * Math.sin(p * Math.PI * 4) * bell(p); } },
  tilt:     { dur: 1.8, fx: (p, r) => { r.roll += 0.2 * bell(p); r.smile += 0.3 * bell(p); } },
  smile:    { dur: 2.2, fx: (p, r) => { r.smile += 0.9 * bell(p); r.squint += 0.35 * bell(p); r.brow += 0.15 * bell(p); } },
  laugh:    { dur: 2.0, fx: (p, r, t) => { const b = bell(p); r.smile += b; r.squint += 0.7 * b; r.open = Math.max(r.open, b * (0.35 + 0.2 * Math.sin(t * 22))); r.pitch -= 0.06 * b; } },
  surprise: { dur: 1.6, fx: (p, r) => { const b = bell(p); r.brow += 0.9 * b; r.eyeScale += 0.35 * b; r.open = Math.max(r.open, 0.45 * b); r.round = Math.max(r.round, 0.8 * b); r.pitch -= 0.05 * b; } },
  wink:     { dur: 0.9, fx: (p, r) => { r.blinkR = Math.max(r.blinkR, bell(p)); r.smile += 0.5 * bell(p); r.roll += 0.06 * bell(p); } },
  look:     { dur: 3.2, fx: (p, r) => { const g = Math.sin(p * Math.PI * 2) * bell(p * 1.0); r.gazeX += 0.9 * g; r.yaw += 0.35 * g; } },
  sad:      { dur: 2.2, fx: (p, r) => { const b = bell(p); r.smile -= 0.8 * b; r.browIn += 0.8 * b; r.pitch += 0.08 * b; r.gazeY -= 0.4 * b; } },
};
export const GESTURE_NAMES = Object.keys(GESTURES);

const MOOD = {
  idle:      { lid: 0.42, smile: 0.12, brow: 0.0, glow: 0.45 },
  listening: { lid: 0.0,  smile: 0.32, brow: 0.12, glow: 0.85 },
  thinking:  { lid: 0.12, smile: 0.0,  brow: 0.25, glow: 1.0 },
};

export function createRig(rnd = Math.random) {
  const life = createLife(rnd);
  const s = {
    t: 0, mood: "listening", gestures: [],
    open: 0, wide: 0, round: 0, press: 0, energy: 0,
    smile: MOOD.listening.smile, lid: 0, brow: 0, glow: 0.8, think: 0,
    blink: 0, blinkAt: -1, nextBlink: 1.5,
    gaze: { x: 0, y: 0 }, gazeTo: { x: 0, y: 0 }, nextSaccade: 1,
  };

  function update(dtMs, frame) {
    const dt = dtMs;
    s.t += dt / 1000;
    const t = s.t;
    const v = frame.visemes || {};
    const speaking = frame.mode === "speaking";
    const m = MOOD[s.mood] || MOOD.listening;

    // ---- mouth from visemes (Oculus set) ----
    const g = (k) => v[k] || 0;
    const open = clamp(g("aa") + g("O") * 0.75 + g("E") * 0.55 + g("U") * 0.45 + g("I") * 0.35
      + (g("DD") + g("kk") + g("nn") + g("TH")) * 0.25 + (g("CH") + g("SS") + g("RR")) * 0.18 + g("FF") * 0.08);
    const wide = clamp(g("E") * 0.8 + g("I") * 0.9 + g("SS") * 0.6 + g("aa") * 0.3 + g("kk") * 0.2
      - g("O") * 0.6 - g("U") * 0.9 - g("CH") * 0.4 - g("RR") * 0.3, -1, 1);
    const round = clamp(g("O") * 0.8 + g("U") + g("RR") * 0.5 + g("CH") * 0.5);
    const press = clamp(g("PP") + g("FF") * 0.4);
    s.open = ease(s.open, open, dt, 35); s.wide = ease(s.wide, wide, dt, 45);
    s.round = ease(s.round, round, dt, 45); s.press = ease(s.press, press, dt, 25);
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
      smile: s.smile, squint: 0, eyeScale: 1, brow: s.brow, browIn: 0,
      blinkL: Math.max(s.blink, s.lid), blinkR: Math.max(s.blink, s.lid),
      gazeX: s.gaze.x, gazeY: s.gaze.y,
      yaw: drift(t * slow, 5) * 0.09 + s.think * 0.14,
      pitch: drift(t * slow, 2) * 0.05 + s.energy * 0.04 * Math.sin(t * 7.3) - s.think * 0.06,
      roll: drift(t * slow, 8) * 0.035 + s.think * 0.07,
      breathe: Math.sin(t * Math.PI * 2 / (s.mood === "idle" ? 5.2 : 4.2)),
    };
    life.apply(r, { t, dt, speaking, mood: s.mood, open, hearing: !!frame.hearing, gesture: (n) => s.gestures.push({ name: n, start: t }) });
    s.gestures = s.gestures.filter((gst) => t - gst.start < GESTURES[gst.name].dur);
    for (const gst of s.gestures) GESTURES[gst.name].fx((t - gst.start) / GESTURES[gst.name].dur, r, t);
    r.smile = clamp(r.smile, -1, 1.2); r.squint = clamp(r.squint);
    r.blinkL = clamp(Math.max(r.blinkL, r.squint * 0.45)); r.blinkR = clamp(Math.max(r.blinkR, r.squint * 0.45));
    if (r.eyeScale > 1) { r.blinkL *= 2 - r.eyeScale; r.blinkR *= 2 - r.eyeScale; }
    return r;
  }

  return {
    update,
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
  function mouth(n = 24) {
    const my = MO.y, mw = 0.2 * MO.k * (1 + 0.35 * r.wide - 0.4 * r.round + 0.15 * Math.max(0, r.smile));
    const h = (0.012 + 0.21 * r.open) * (1 - r.press * 0.9) * Math.sqrt(MO.k);
    const c = r.smile * 0.07 * MO.k;
    const upper = [], lower = [];
    for (let i = 0; i <= n; i++) {
      const k = (i / n) * 2 - 1, body = 1 - k * k;
      const roundBody = Math.sqrt(Math.max(0, body));
      const prof = body * (1 - r.round) + roundBody * r.round;
      upper.push([k * mw, my + c * k * k + 0.25 * h * prof]);
      lower.push([k * mw, my + c * k * k - 0.75 * h * prof - c * 0.4 * body]);
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
