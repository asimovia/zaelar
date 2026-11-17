// temperament.js — TEMPERAMENT, the pure half: whether and how the face answers what it perceived. It is not a mirror.
// A small mood — ENGAGEMENT (0..1) rises with every exchange and decays when he goes quiet — and a seeded randomness pick
// among weighted answers, where «nothing» is always one of them: an engaged face answers more often, a fresh one
// shrugs more gestures off, and the same gesture again and again gets tired answers (a sigh, a glance away) and then
// none. Cooldowns keep it from chattering: a gap between any two answers, and the same answer never twice in a row
// within a while. Answers take a human beat to come (a random 120–380 ms), and a FIRST gesture is almost always answered. While the agent SPEAKS its mouth belongs to
// the voice, so the answers that use the mouth (laugh, tongue, yawn) are swapped for ones that do not.
// No DOM, no clock: the caller passes the time; with a seed (tests) the same events give the same answers.

/** A small seeded generator (mulberry32): `seeded(42)()` → 0..1, the same sequence for the same seed. */
export function seeded(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// perceived event → weighted answers (`null` = it lets this one go). The weights are the character.
export const ANSWERS = {
  smile:    { smile: 7, tilt: 1.5, shy: 1.2, null: 2.5 },
  laugh:    { laugh: 5, giggle: 3, smile: 2, null: 1 },
  wink:     { wink: 8, smile: 2, brows: 1, null: 2 },
  tongue:   { tongue: 5, laugh: 2, surprise: 1, null: 2 },
  yawn:     { yawn: 1.5, sigh: 1.5, null: 7 },
  surprise: { surprise: 4, brows: 2, null: 2.5 },
  brows:    { brows: 4, tilt: 1, null: 3.5 },
  nod:      { nod: 4, smile: 1, null: 3 },
  shake:    { shake: 1.5, tilt: 2, sad: 1, null: 3 },
  arrive:   { hello: 6, smile: 2, null: 1 },
  leave:    { sigh: 2, look: 2, null: 3 },
  hand:     { hello: 5, smile: 2, null: 1 },     // declared: no hand detector ships yet (hands.js)
};
const TIRED = { sigh: 1, look: 1.2, null: 6 };    // the same gesture once too often
const MOUTH = new Set(["laugh", "giggle", "tongue", "yawn"]);
const QUIET_SWAP = { laugh: "smile", giggle: "smile", tongue: "brows", yawn: null };
// A FIRST gesture (none of its kind for `tiredMs`) is almost always answered — the moment he tries something the face
// must show it noticed (2026-11-18: «it follows me, but it does not feel it reacts to me»). Letting go is for repeats.
// These keep their full «nothing»: a yawn, a departure, a brow, a nod are not invitations.
const SHY = new Set(["yawn", "leave", "brows", "nod"]);

export const TEMPER = {
  rise: 0.18, halfLifeMs: 45000,          // engagement: each exchange adds, then it halves every 45 s
  gapMs: 1200, sameMs: 5000, tiredAfter: 3, tiredMs: 20000, fresh: 0.25,
  delayMs: [120, 380],
};

export function createTemperament(opts = {}) {
  const k = { ...TEMPER, ...opts };
  const R = typeof opts.rng === "function" ? opts.rng : Math.random;
  let engagement = 0, at = null, lastAnswerAt = -Infinity, lastAnswer = null, runs = {};

  function decay(t) {
    if (at !== null) engagement *= Math.pow(0.5, Math.max(0, t - at) / k.halfLifeMs);
    at = t;
  }
  function pick(w) {
    let tot = 0; for (const n in w) tot += w[n];
    let x = R() * tot;
    for (const n in w) { x -= w[n]; if (x <= 0) return n === "null" ? null : n; }
    return null;
  }

  /**
   * A perceived event at time `t`. `speaking` = the agent's voice is on. → `{answer, delayMs}` or null (let go).
   * `answer` is a name the expression layer knows (expression.js).
   */
  function hear(ev, t, { speaking = false } = {}) {
    const base = ANSWERS[ev.type];
    if (!base) return null;
    decay(t);
    // repetition: the same gesture within `tiredMs` of the last one counts up; past `tiredAfter` the answers tire
    const run = runs[ev.type];
    runs[ev.type] = run && t - run.t < k.tiredMs ? { n: run.n + 1, t } : { n: 1, t };
    const tired = runs[ev.type].n > k.tiredAfter, fresh = runs[ev.type].n === 1 && !SHY.has(ev.type);
    engagement = Math.min(1, engagement + (tired ? 0.02 : k.rise));
    if (t - lastAnswerAt < k.gapMs) return null;                       // still answering the last one
    const w = { ...(tired ? TIRED : base) };
    // a fresh face lets more go; an engaged one lets less go (×1.6 at 0 engagement, ×0.6 at full)
    if (w.null) w.null *= (1.6 - engagement) * (fresh ? k.fresh : 1);
    for (const n in w) if (n !== "null" && n === lastAnswer && t - lastAnswerAt < k.sameMs) w[n] = 0;
    let answer = pick(w);
    if (answer && speaking && MOUTH.has(answer)) answer = QUIET_SWAP[answer];
    if (!answer) return null;
    lastAnswer = answer; lastAnswerAt = t;
    return { answer, delayMs: Math.round(k.delayMs[0] + R() * (k.delayMs[1] - k.delayMs[0])), of: ev.type };
  }

  return { hear, get engagement() { return engagement; } };
}
