// look.js — «look at me» (V2-928 T10), the PURE half: where the person is, as one smoothed GAZE the rig can turn to.
// Two sources feed it, both on the device and neither ever sending an image or a number anywhere:
//   * the CAMERA (look-camera.js): face boxes from an on-device detector, in the raw camera frame (0..1);
//   * the HEADPHONES (head-motion.js, iPhone + AirPods through the native app): the person's head orientation.
// Out comes `{x, y, w}`: the gaze the drawn face should take, in RADIANS — x > 0 = toward the screen's right as the
// person sees it, y > 0 = up — and w (0..1) how much the face should follow: 1 while the person is seen, fading to 0
// when they are lost, so the face falls back to its own idle life (life.js) instead of freezing on the last place.
// No DOM and no timers here: every call takes the time, so a test can drive it frame by frame.
//
// THE GEOMETRY (2026-11-17, the operator: «at the sides it swings too far, it no longer looks at me»). The camera is a
// pinhole: from a box's centre and size and the lens's field of view come his direction AND his distance (a face is
// about `faceW` wide), so his eyes are a point in front of the screen. The face is drawn at the screen's centre, below
// the camera (`camAbove`), so that point is re-aimed from there. Then the one correction a FLAT face needs: a painted
// face that looks straight out seems to look at every viewer wherever they stand (the Mona Lisa effect), so turning it
// by his true angle makes it look PAST him. Only a share (`flat`) of the true angle is drawn — enough to be seen
// following, small enough that the eyes still meet his — and the rig gives most of it to the eyes, a little to the head.

const clamp = (v, a = -1, b = 1) => Math.max(a, Math.min(b, v));
const toward = (cur, target, dtMs, tauMs) => cur + (target - cur) * (1 - Math.exp(-Math.max(0, dtMs) / tauMs));
const DEG = Math.PI / 180;

/** Tuning, one place. Times in ms, angles in radians, lengths in metres. */
export const LOOK = {
  hfov: 62 * DEG,      // a laptop / phone front camera's horizontal field of view (60–70°; a browser does not report it)
  aspect: 0.75,        // frame height over width when a detection does not say (240×180)
  faceW: 0.16,         // a face box's real width: with the box's size it gives his distance
  eyeUp: 0.12,         // his eyes sit this share of the box above its centre
  camAbove: 0.1,       // the camera sits this far above the drawn face (the screen's centre)
  flat: 0.35,          // the share of his true angle a FLAT face draws (the Mona Lisa effect, above)
  maxX: 0.2,           // the drawn gaze never goes past these (≈11° sideways, ≈7° up or down)
  maxY: 0.12,
  smoothMs: 160,       // the raw angle is low-passed first (the detector jitters a few pixels per frame)
  dead: 0.035,         // then a dead band on his TRUE angle (≈2°): a smaller move does not move the target at all
  holdMs: 900,         // a lost face keeps the target this long (a blink of the detector is not a departure)
  fadeMs: 1200,        // then the weight fades to 0 and the idle life takes the head back
  headZeroMs: 30000,   // the headphones' zero follows a long-held pose very slowly (he turned his chair)
};

const sign = (v) => (v < 0 ? -1 : 1);

/** A dead band that FOLLOWS: inside the band nothing moves; outside it the held value trails by the band. */
function band(held, v, dead) {
  const d = v - held;
  return Math.abs(d) <= dead ? held : v - sign(d) * dead;
}

/**
 * His eyes' TRUE direction from the drawn face, from one detection `{x, y, size, ar?}` (raw frame, 0..1; size = the
 * box side over the frame width; ar = frame height over width). → `{yaw, pitch, dist}`: yaw > 0 = toward the screen's
 * right as he sees it (the raw frame is not mirrored: his left is the frame's right), pitch > 0 = up, dist in metres.
 */
export function direction(d, k = LOOK) {
  const t = Math.tan(k.hfov / 2), ar = d.ar > 0 ? d.ar : k.aspect, tv = t * ar;
  const size = Math.max(0.02, d.size || 0);
  const Z = k.faceW / (2 * size * t);                       // his distance: the box's angular width against a face's
  const X = (0.5 - d.x) * 2 * t * Z;                        // sideways, as he sees the screen
  const eyeY = d.y - (k.eyeUp * size) / ar;                 // his eyes, a little above the box's centre
  const Y = (0.5 - eyeY) * 2 * tv * Z + k.camAbove;         // up from the drawn face, which sits below the camera
  return { yaw: Math.atan2(X, Z), pitch: Math.atan2(Y, Z), dist: Z };
}

/** The gaze a flat face draws for a true direction: a share of it, clamped (see THE GEOMETRY). */
export function drawn(yaw, pitch, k = LOOK) {
  return { x: clamp(yaw * k.flat, -k.maxX, k.maxX), y: clamp(pitch * k.flat, -k.maxY, k.maxY) };
}

/**
 * The camera's tracker. `feed(dets, t)` with the frame's faces: `[{x, y, size, q, ar?}]`, x/y the box centre in the RAW
 * camera frame (0..1, not mirrored — the camera looks back at the person, so their left is the frame's right), size
 * the box side over the frame width, q the detector's score. `sample(t)` → `{x, y, w}` (the drawn gaze, radians).
 */
export function createTracker(opts = {}) {
  const k = { ...LOOK, ...opts };
  let fyaw = 0, fpit = 0, hyaw = 0, hpit = 0, seenAt = -Infinity, lastT = null, has = false, size = 0;

  function pick(dets) {
    if (!dets || !dets.length) return null;
    if (!has) return dets.reduce((a, b) => (b.size > a.size ? b : a));        // first sight: the nearest face
    // already following someone: stay with the face closest to where they were (another person walking by behind
    // does not steal the gaze), unless a clearly nearer one stands in front
    const near = (d) => Math.hypot(direction(d, k).yaw - fyaw, d.size - size);
    return dets.reduce((a, b) => (near(b) < near(a) ? b : a));
  }

  return {
    feed(dets, t) {
      const dt = lastT == null ? 0 : t - lastT; lastT = t;
      const d = pick(dets);
      if (!d) return;
      const g = direction(d, k);
      if (!has) { fyaw = hyaw = g.yaw; fpit = hpit = g.pitch; has = true; }
      else { fyaw = toward(fyaw, g.yaw, dt, k.smoothMs); fpit = toward(fpit, g.pitch, dt, k.smoothMs); }
      hyaw = band(hyaw, fyaw, k.dead);
      hpit = band(hpit, fpit, k.dead);
      size = d.size; seenAt = t;
    },
    sample(t) {
      if (!has) return { x: 0, y: 0, w: 0 };
      const gone = t - seenAt - k.holdMs;
      const w = gone <= 0 ? 1 : Math.max(0, 1 - gone / k.fadeMs);
      if (w === 0) { has = false; return { x: 0, y: 0, w: 0 }; }   // the next sight starts afresh
      return { ...drawn(hyaw, hpit, k), w };
    },
    get seen() { return has; },
  };
}

/**
 * The headphones' tracker: the person's head orientation `{yaw, pitch, t}` (radians; yaw > 0 = they turn to THEIR
 * right, pitch > 0 = they look up) relative to a zero taken from the first samples and re-centred very slowly, so the
 * face turns where they turn — by the same flat share as the camera's gaze. It cannot know where they STAND, only
 * where they look.
 */
export function createHeadTracker(opts = {}) {
  const k = { ...LOOK, ...opts };
  let zy = null, zp = 0, yaw = 0, pit = 0, seenAt = -Infinity, lastT = null;
  return {
    feed(m, t) {
      if (!Number.isFinite(m.yaw) || !Number.isFinite(m.pitch)) return;
      const dt = lastT == null ? 0 : t - lastT; lastT = t;
      if (zy == null) { zy = m.yaw; zp = m.pitch; }
      zy = toward(zy, m.yaw, dt, k.headZeroMs); zp = toward(zp, m.pitch, dt, k.headZeroMs);
      // wrap the yaw difference into (-π, π]: a turn across the sensor's ±π seam is a small turn, not a full one
      let dy = m.yaw - zy; dy = Math.atan2(Math.sin(dy), Math.cos(dy));
      yaw = band(yaw, dy, k.dead * 0.5);
      pit = band(pit, m.pitch - zp, k.dead * 0.5);
      seenAt = t;
    },
    /** Forget the zero: the next sample is «straight ahead» (the switch turned on again). */
    recenter() { zy = null; yaw = 0; pit = 0; lastT = null; },
    sample(t) {
      const gone = t - seenAt - k.holdMs;
      const w = gone <= 0 ? 1 : Math.max(0, 1 - gone / k.fadeMs);
      return { ...drawn(yaw, pit, k), w };
    },
  };
}

/** One target from both sources: the camera wins while it sees someone; the headphones fill in otherwise. */
export function blend(cam, head) {
  const c = cam || { w: 0 }, h = head || { w: 0 };
  if (c.w >= 0.5 || c.w >= h.w) return c.w > 0 ? c : (h.w > 0 ? h : null);
  return h;
}
