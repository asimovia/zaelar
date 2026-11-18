// humanity/ — «the face answers you» (V2-928 T12): the agent's body language. Three parts, one direction:
//   PERCEPTION  (perceive.js)   what he just did in front of the camera → events (smile, laugh, wink, tongue, yawn,
//                                «oh!», brows, nod, shake, arrive, leave; hand: declared, hands.js);
//   TEMPERAMENT (temperament.js) whether and how to answer — engagement, cooldowns, a seeded pick where «nothing» is
//                                always an option: another being, not a mirror;
//   EXPRESSION  (expression.js) the answer as the face rig's gestures.
// The camera feeds it (look-camera.js): face boxes from either detector for presence, and — once the vendored MediaPipe
// Face Landmarker has loaded (landmarker.js) — the 52 expression scores and a head pose. This module is imported only
// when the camera starts (LookAtMe.js), so a switch that is off loads none of it. Nothing it reads or decides leaves the
// page but the NAMES of what he did and what the face answered (recent.js → the engine words them for the model);
// the seam that would let the agent speak up about the play (remark.js) is OFF and wired to nothing unless its switch is on.
import { createPerceiver } from "./perceive.js?v=1";
import { createTemperament, seeded } from "./temperament.js?v=1";
import { createExpression } from "./expression.js?v=1";
import { createRemarker } from "./remark.js?v=1";
import { loadLandmarker, readResult } from "./landmarker.js?v=1";
import { note } from "../recent.js?v=1";

const KEY = "hb_presence_humanity";
/** The seam's switch (per device, off unless set by hand): may a stretch's summary be offered to the conversation? */
export function talkOn() {
  try { const d = JSON.parse(localStorage.getItem(KEY) || "{}"); return !!(d && d.talk === true); } catch (_) { return false; }
}

/**
 * The humanity of one face. `face` has `gesture(name)`; `speech()` → `{hearing, speaking}` (his mic hears him · the
 * agent's voice is on); `offer(summary)` is the seam's far end (called only with talkOn()). `rng` seeds the character.
 */
export function createHumanity(face, { speech = () => ({}), rng = null, offer = null, setTimer = setTimeout, clearTimer = clearTimeout } = {}) {
  const R = rng || seeded(((Date.now() & 0xffffffff) ^ Math.floor(Math.random() * 0xffffffff)) >>> 0);
  const perceiver = createPerceiver(), temper = createTemperament({ rng: R }), expr = createExpression(face, { rng: R });
  const remarker = createRemarker({ rng: R, offer: (s) => { if (offer && talkOn()) offer(s); } });
  const timers = new Set(), log = [];
  let disposed = false;
  const keep = (x) => { log.push(x); if (log.length > 30) log.shift(); };
  return {
    /** One analysed frame: `faces` = `[{size, shapes?, pose?}]` (or [] for nobody), `t` in ms. → the events it completed. */
    frame(faces, t) {
      if (disposed) return [];
      const sp = speech() || {};
      const evs = perceiver.feed({ faces, hearing: !!sp.hearing, speaking: !!sp.speaking }, t);
      for (const ev of evs) {
        remarker.note(ev, t);
        const a = temper.hear(ev, t, { speaking: !!sp.speaking });
        keep({ t: Math.round(t), saw: ev.type, side: ev.side, answer: a ? a.answer : null });
        note("saw", ev.type);                       // for the model: what he did (recent.js), by name only
        if (!a) continue;
        const id = setTimer(() => {
          timers.delete(id);
          if (disposed) return;
          expr.play(a.answer, ev);
          note("did", a.answer, { why: "answer", of: ev.type });
        }, a.delayMs);
        timers.add(id);
      }
      return evs;
    },
    get engagement() { return temper.engagement; },
    get log() { return log.slice(); },
    dispose() { disposed = true; for (const id of timers) clearTimer(id); timers.clear(); },
  };
}

/** The camera's rich detector: the Face Landmarker on a video element. → `{detect(video, t) → {dets, faces}, delegate}`. */
export async function meshDetector() {
  const lm = await loadLandmarker();
  let last = 0;
  return {
    delegate: lm.delegate,
    detect(video, t) {
      const ts = Math.max(last + 1, Math.round(t)); last = ts;
      return readResult(lm.detectForVideo(video, ts), video.videoWidth || 1, video.videoHeight || 1);
    },
  };
}
