// life.js — the face is never a statue (V2-928). Two sources of motion on top of the rig's slow drift:
//  * ACTIONS while it waits, listens or thinks: a random pick from a small vocabulary of poses (glance, look up,
//    look down, think, tilt, smile, brow flash, settle), each with a random amplitude, side and duration, at random
//    intervals whose range depends on the mood. While the person is speaking it gives small nods (backchannel).
//  * EMPHASIS while it speaks: a rise of the voice's energy after a calmer stretch fires one accent (nod, brow raise,
//    tilt, turn, smile, lean), never the same one twice in a row, then waits a random refractory gap.
// Calmer since 2026-11-18 (the operator: «the face moves up and down a lot, as if saying yes, very exaggerated»): the
// nods are half as deep and rarer, an accent no longer fires a whole nod, and a nod is kept for when it means yes.
// Nothing here is a fixed loop: every interval, amplitude and choice is drawn, so no two minutes look alike.
// The rig hands `apply()` the frame's numbers; this adds offsets to them and may start one of the rig's gestures.

const smooth = (x) => (x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x));
const env = (p, a = 0.22, rel = 0.3) => (p < a ? smooth(p / a) : p > 1 - rel ? smooth((1 - p) / rel) : 1);

// pose(a, side, R) → offsets added to the rig; `a` is the amplitude (0.5..1.2), `side` ±1, R a random draw.
const POSES = {
  glance:   (a, s, R) => ({ gazeX: 0.85 * s * a, gazeY: (R() - 0.5) * 0.7 * a, yaw: 0.1 * s * a }),
  lookUp:   (a, s) => ({ gazeY: 0.75 * a, gazeX: 0.35 * s * a, pitch: -0.07 * a, brow: 0.25 * a }),
  lookDown: (a, s) => ({ gazeY: -0.6 * a, gazeX: 0.2 * s * a, pitch: 0.08 * a }),
  think:    (a, s) => ({ gazeY: 0.8 * a, gazeX: 0.7 * s * a, browIn: 0.45 * a, squint: 0.25 * a, roll: 0.07 * s * a, yaw: 0.08 * s * a }),
  tilt:     (a, s) => ({ roll: 0.13 * s * a, smile: 0.15 * a, gazeX: -0.2 * s * a }),
  smile:    (a) => ({ smile: 0.55 * a, squint: 0.2 * a, brow: 0.08 * a }),
  brow:     (a) => ({ brow: 0.6 * a, eyeScale: 0.08 * a }),
  settle:   (a, s) => ({ pitch: 0.05 * a, roll: -0.05 * s * a, lid: 0.25 * a }),
  nod:      (a) => ({ pitch: 0.045 * a }),
  // speech accents (short)
  accNod:   (a) => ({ pitch: 0.045 * a, brow: 0.1 * a }),
  accBrow:  (a) => ({ brow: 0.75 * a, eyeScale: 0.07 * a }),
  accTilt:  (a, s) => ({ roll: 0.11 * s * a, brow: 0.2 * a }),
  accTurn:  (a, s) => ({ yaw: 0.16 * s * a, gazeX: -0.3 * s * a }),
  accSmile: (a) => ({ smile: 0.5 * a, squint: 0.15 * a }),
  accLean:  (a) => ({ pitch: -0.06 * a, brow: 0.35 * a, eyeScale: 0.05 * a }),
};
// weights per situation, and the gap (seconds) between two actions
const PLAN = {
  idle:      { gap: [1.8, 5.5], w: { glance: 3, lookUp: 1.4, lookDown: 1.4, tilt: 2, settle: 1.2, smile: 0.8, think: 0.5 } },
  listening: { gap: [2.2, 6], w: { glance: 2.4, tilt: 1.6, smile: 1.4, brow: 1, lookUp: 0.6, lookDown: 0.4 } },
  hearing:   { gap: [2.2, 5], w: { nod: 1.4, brow: 1, smile: 1, tilt: 0.8, glance: 0.8 } },
  thinking:  { gap: [1.2, 3.2], w: { think: 4, lookUp: 2, tilt: 1, glance: 0.6 } },
};
const ACCENTS = ["accNod", "accBrow", "accTilt", "accTurn", "accSmile", "accLean"];
const KEYS = ["gazeX", "gazeY", "yaw", "pitch", "roll", "brow", "browIn", "smile", "squint", "eyeScale", "lid"];

export function createLife(R = Math.random) {
  const between = (a, b) => a + R() * (b - a);
  const pick = (w) => { let tot = 0; for (const k in w) tot += w[k]; let x = R() * tot; for (const k in w) { x -= w[k]; if (x <= 0) return k; } return Object.keys(w)[0]; };
  let acts = [];                       // running poses: { off, start, dur }
  let next = between(0.8, 2.5), lastAcc = "", accAt = -9, accGap = 1, fast = 0, slow = 0, wasSpeaking = false;

  function start(name, t, dur, amp) {
    acts.push({ off: POSES[name](amp, R() < 0.5 ? -1 : 1, R), start: t, dur });
  }

  function apply(r, f) {
    const { t, dt, speaking, mood, open, hearing } = f;
    // ---- emphasis while speaking: energy rising over its own recent average
    fast += (open - fast) * (1 - Math.exp(-dt / 60));
    slow += (open - slow) * (1 - Math.exp(-dt / 900));
    if (speaking) {
      if (!wasSpeaking && R() < 0.5) start(R() < 0.5 ? "accBrow" : "accLean", t, between(0.5, 0.9), between(0.5, 0.9));
      if (t - accAt > accGap && fast > slow * 1.35 + 0.08) {
        let name; do name = ACCENTS[Math.floor(R() * ACCENTS.length)]; while (name === lastAcc);
        start(name, t, between(0.35, 0.8), between(0.6, 1.15));
        if (R() < 0.12) f.gesture("smile");
        lastAcc = name; accAt = t; accGap = between(1.0, 2.4);
      }
      next = Math.max(next, t + between(0.6, 1.8));          // idle actions wait for the voice to end
    } else {
      if (wasSpeaking && R() < 0.5) start(R() < 0.8 ? "smile" : "nod", t, between(0.8, 1.6), between(0.5, 0.9));
      if (t >= next) {
        const plan = PLAN[hearing ? "hearing" : mood] || PLAN.listening;
        start(pick(plan.w), t, between(0.9, 2.6), between(0.5, 1.2));
        next = t + between(plan.gap[0], plan.gap[1]);
      }
    }
    wasSpeaking = speaking;
    // ---- sum the running poses into this frame
    acts = acts.filter((a) => t - a.start < a.dur);
    for (const a of acts) {
      const e = env((t - a.start) / a.dur);
      for (const k of KEYS) if (a.off[k]) {
        if (k === "lid") { r.blinkL = Math.max(r.blinkL, a.off.lid * e); r.blinkR = Math.max(r.blinkR, a.off.lid * e); }
        else r[k] += a.off[k] * e;
      }
    }
  }

  return { apply, get running() { return acts.length; } };
}
