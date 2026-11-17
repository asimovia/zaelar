// remark.js — the SEAM to the conversation, declared and OFF. Today the face answers him with its body only: zero
// model, zero tokens. The future step: after a stretch of sustained visual play — a random 20–60 s of exchanges with no
// long pause — the agent may SAY something in character («you've been making faces at me for forty seconds…»). This
// file builds that stretch's tiny summary (counts and seconds, never an image, never a frame's numbers) and offers it
// ONCE per stretch to `offer` — which the caller wires to nothing unless the switch `talk` is on, and even then the
// brain's end (turning the summary into one line in his personality) is not built yet. See the module doc.

/** Words for the summary's English line (the brain would say it in his language). */
const VERB = { smile: "smiling", laugh: "laughing", wink: "winking", tongue: "sticking his tongue out",
  yawn: "yawning", surprise: "making surprised faces", brows: "raising his brows", nod: "nodding", shake: "shaking his head",
  hand: "waving" };

export const STRETCH = { gapMs: 10000, minMs: 20000, maxMs: 60000, coolMs: 600000 };

/** The summary of a stretch: `{seconds, counts, line}`. Pure. */
export function summarize(counts, ms) {
  const seconds = Math.round(ms / 1000);
  const parts = Object.entries(counts).filter(([k]) => VERB[k]).sort((a, b) => b[1] - a[1]).map(([k, n]) => `${VERB[k]} (${n})`);
  return { seconds, counts: { ...counts },
    line: `He has been playing with your face for ${seconds} s: ${parts.join(", ") || "looking at you"}.` };
}

export function createRemarker({ rng = Math.random, offer = () => {}, ...opts } = {}) {
  const k = { ...STRETCH, ...opts };
  let start = null, last = -Infinity, counts = {}, due = 0, offered = false, coolUntil = -Infinity;
  return {
    /** A perceived event (not presence) at `t`. Offers the stretch's summary once, when it has lasted its drawn length. */
    note(ev, t) {
      if (ev.type === "arrive" || ev.type === "leave") return null;
      if (t - last > k.gapMs) { start = t; counts = {}; offered = false; due = k.minMs + rng() * (k.maxMs - k.minMs); }
      last = t;
      counts[ev.type] = (counts[ev.type] || 0) + 1;
      if (offered || t < coolUntil || t - start < due) return null;
      offered = true; coolUntil = t + k.coolMs;
      const s = summarize(counts, t - start);
      try { offer(s); } catch (_) {}
      return s;
    },
  };
}
