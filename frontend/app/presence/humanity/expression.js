// expression.js — EXPRESSION: an answer (temperament.js) as the face rig's gestures (rig.js GESTURES). Composite
// answers play more than one gesture (a «hello» is the brow flash every human greeting starts with, then a smile). A
// wink back is usually with the eye on the side he winked — as he sees it, a mirror — and sometimes with the other.
// No DOM: `play(answer, ev)` returns the gesture names it started on `face` (anything with a `gesture(name)`).

export const PLAYS = {
  smile: ["smile"], laugh: ["laugh"], giggle: ["giggle"], tongue: ["tongue"], yawn: ["yawn"], sigh: ["sigh"],
  surprise: ["surprise"], brows: ["brows"], tilt: ["tilt"], nod: ["nod"], shake: ["shake"], sad: ["sad"],
  look: ["look"], shy: ["look", "smile"], hello: ["brows", "smile"], wink: null,
};
export const ANSWER_NAMES = Object.keys(PLAYS);

export function createExpression(face, { rng = Math.random } = {}) {
  return {
    /** Play `answer` (a name of PLAYS) for the perceived `ev`. → the rig gestures started. */
    play(answer, ev = {}) {
      let names = PLAYS[answer];
      if (answer === "wink") {
        // `side` is HIS eye (the blendshapes' convention: eyeBlinkLeft = the person's left eye). He faces the screen,
        // so his left eye is on the screen's left: the face mirrors him with the eye on that side (`winkL`, the
        // viewer's left) three times in four, and winks the other one otherwise
        const mirror = rng() < 0.75;
        const hisLeft = ev.side === "left";
        names = [(hisLeft === mirror) ? "winkL" : "wink"];
      }
      if (!names) return [];
      for (const n of names) face.gesture(n);
      return names;
    },
  };
}
