// look.js — «look at me» (V2-928 T10), the PURE half: where the person is, as one smoothed target the rig can turn to.
// Two sources feed it, both on the device and neither ever sending an image or a number anywhere:
//   * the CAMERA (look-camera.js): face boxes from an on-device detector, in the raw camera frame (0..1);
//   * the HEADPHONES (head-motion.js, iPhone + AirPods through the native app): the person's head orientation.
// Out comes `{x, y, w}`: x > 0 = the person is to the screen's right as THEY see it, y > 0 = up, both -1..1, and w (0..1)
// how much the face should follow — 1 while the person is seen, fading to 0 when they are lost, so the face falls back
// to its own idle life (life.js) instead of freezing on the last place it saw someone.
// No DOM and no timers here: every call takes the time, so a test can drive it frame by frame.

const clamp = (v, a = -1, b = 1) => Math.max(a, Math.min(b, v));
const toward = (cur, target, dtMs, tauMs) => cur + (target - cur) * (1 - Math.exp(-Math.max(0, dtMs) / tauMs));

/** Tuning, one place. Times in ms. */
export const LOOK = {
  smoothMs: 160,       // the raw position is low-passed first (the detector jitters a few pixels per frame)
  dead: 0.06,          // then a dead band: a move smaller than this does not move the target at all
  holdMs: 900,         // a lost face keeps the target this long (a blink of the detector is not a departure)
  fadeMs: 1200,        // then the weight fades to 0 and the idle life takes the head back
  yBaseMs: 8000,       // the camera sits above the screen: the person's USUAL height drifts in as the zero for y
  yGain: 0.8,
  headYaw: 0.7,        // the headphones: radians of the person's turn that reach the edge (x = ±1)
  headPitch: 0.45,
  headZeroMs: 30000,   // the headphones' zero follows a long-held pose very slowly (he turned his chair)
};

const sign = (v) => (v < 0 ? -1 : 1);

/** A dead band that FOLLOWS: inside the band nothing moves; outside it the held value trails by the band. */
function band(held, v, dead) {
  const d = v - held;
  return Math.abs(d) <= dead ? held : v - sign(d) * dead;
}

/**
 * The camera's tracker. `feed(dets, t)` with the frame's faces: `[{x, y, size, q}]`, x/y the box centre in the RAW
 * camera frame (0..1, not mirrored — the camera looks back at the person, so their left is the frame's right), size
 * the box side over the frame width, q the detector's score. `sample(t)` → `{x, y, w}`.
 */
export function createTracker(opts = {}) {
  const k = { ...LOOK, ...opts };
  let fx = 0, fy = 0, hx = 0, hy = 0, yBase = null, seenAt = -Infinity, lastT = null, has = false, size = 0;

  function pick(dets) {
    if (!dets || !dets.length) return null;
    if (!has) return dets.reduce((a, b) => (b.size > a.size ? b : a));        // first sight: the nearest face
    // already following someone: stay with the face closest to where they were (another person walking by behind
    // does not steal the gaze), unless a clearly nearer one stands in front
    const near = (d) => Math.hypot((0.5 - d.x) * 2 - fx, d.size - size);
    return dets.reduce((a, b) => (near(b) < near(a) ? b : a));
  }

  return {
    feed(dets, t) {
      const dt = lastT == null ? 0 : t - lastT; lastT = t;
      const d = pick(dets);
      if (!d) return;
      const rx = clamp((0.5 - d.x) * 2), ry = clamp((0.5 - d.y) * 2);
      if (!has) { fx = rx; fy = ry; hx = rx; yBase = ry; has = true; }
      else { fx = toward(fx, rx, dt, k.smoothMs); fy = toward(fy, ry, dt, k.smoothMs); }
      yBase = toward(yBase, fy, dt, k.yBaseMs);
      hx = band(hx, fx, k.dead);
      hy = band(hy, clamp((fy - yBase) * k.yGain), k.dead);
      size = d.size; seenAt = t;
    },
    sample(t) {
      if (!has) return { x: 0, y: 0, w: 0 };
      const gone = t - seenAt - k.holdMs;
      const w = gone <= 0 ? 1 : Math.max(0, 1 - gone / k.fadeMs);
      if (w === 0) { has = false; return { x: 0, y: 0, w: 0 }; }   // the next sight starts afresh
      return { x: hx, y: hy, w };
    },
    get seen() { return has; },
  };
}

/**
 * The headphones' tracker: the person's head orientation `{yaw, pitch, t}` (radians; yaw > 0 = they turn to THEIR
 * right, pitch > 0 = they look up) relative to a zero taken from the first samples and re-centred very slowly, so the
 * face turns where they turn. It cannot know where they STAND — only where they look.
 */
export function createHeadTracker(opts = {}) {
  const k = { ...LOOK, ...opts };
  let zy = null, zp = 0, x = 0, y = 0, seenAt = -Infinity, lastT = null;
  return {
    feed({ yaw, pitch }, t) {
      if (!Number.isFinite(yaw) || !Number.isFinite(pitch)) return;
      const dt = lastT == null ? 0 : t - lastT; lastT = t;
      if (zy == null) { zy = yaw; zp = pitch; }
      zy = toward(zy, yaw, dt, k.headZeroMs); zp = toward(zp, pitch, dt, k.headZeroMs);
      // wrap the yaw difference into (-π, π]: a turn across the sensor's ±π seam is a small turn, not a full one
      let dy = yaw - zy; dy = Math.atan2(Math.sin(dy), Math.cos(dy));
      x = band(x, clamp(dy / k.headYaw), k.dead * 0.5);
      y = band(y, clamp((pitch - zp) / k.headPitch), k.dead * 0.5);
      seenAt = t;
    },
    /** Forget the zero: the next sample is «straight ahead» (the switch turned on again). */
    recenter() { zy = null; x = 0; y = 0; lastT = null; },
    sample(t) {
      const gone = t - seenAt - k.holdMs;
      const w = gone <= 0 ? 1 : Math.max(0, 1 - gone / k.fadeMs);
      return { x, y, w };
    },
  };
}

/** One target from both sources: the camera wins while it sees someone; the headphones fill in otherwise. */
export function blend(cam, head) {
  const c = cam || { w: 0 }, h = head || { w: 0 };
  if (c.w >= 0.5 || c.w >= h.w) return c.w > 0 ? c : (h.w > 0 ? h : null);
  return h;
}
