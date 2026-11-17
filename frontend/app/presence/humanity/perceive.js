// perceive.js — PERCEPTION, the pure half: what the person in front of the camera just DID, as discrete events.
// In: per analysed frame, the faces the detector saw — `{size, shapes?, pose?}` (shapes = MediaPipe's 52 blendshape
// scores, pose = head yaw/pitch proxies; both absent with the light detector, which only says a face is there) — plus
// whether he is talking (his microphone) and whether the agent is speaking. Out: events `{type, t, side?}`.
// No DOM, no timers, no randomness: every call takes the time, so a test drives it frame by frame.
//
// What is NOT an event is the point of this file. Speech moves the mouth all the time, so every MOUTH reading (smile,
// laugh, yawn, tongue, «oh!») is muted while he talks — heard by his microphone OR seen as the jaw's 3–8 Hz flutter,
// so a muted mic does not let his talking through — and for a moment after. A laugh is the one mouth event allowed
// while he makes sound, and only with a big smile held. Every event must be HELD for a while (a blink is not a wink,
// a word is not a yawn) and re-arms only after the face lets it go.

/** Thresholds, one place (MediaPipe blendshape scores are 0..1). */
export const SENSE = {
  smile: 0.5, smileMs: 300,              // mean of mouthSmileLeft/Right, held
  laughSmile: 0.6, laughJaw: 0.2, laughMs: 300,
  // a real wink (measured feel, 2026-11-18): the shut eye reads ~0.4–0.7 and the open one rises too (the cheek squints)
  winkClosed: 0.38, winkOpen: 0.35, winkGap: 0.15, winkMs: 120, winkMaxMs: 1400,
  tongue: 0.3, tongueMs: 260,
  yawnJaw: 0.58, yawnMs: 1100,
  ohJaw: 0.35, ohBrow: 0.45, ohMs: 320,  // jaw open + brows up = «oh!»
  brows: 0.5, browsMs: 220,              // browInnerUp or the outer brows' mean
  releaseMs: 280,                        // a held state must let go this long before it can fire again…
  letGo: 0.7,                            // …and «let go» means under this share of its threshold (a held smile that
                                         // hovers at the line is ONE smile, not one every few seconds)
  talkWindowMs: 1500, talkSwings: 4, talkAmp: 0.07, quietMs: 900,
  // a nod is two clear swings of the pitch; a SHAKE needs three wide ones — turning to look around, or settling in the
  // chair, is one or two swings and must never read as «no» (2026-11-18: the face kept saying no out of the blue)
  nodWindowMs: 1600, nodAmp: 0.04, shakeAmp: 0.09, shakeSwings: 3,
  arriveMs: 700, awayMs: 4000, absentMs: 30000,
};

const S = (sh, k) => (sh && sh[k]) || 0;

/** Count direction changes of a series whose swings are at least `amp` (a nod is down-up-down, a shake left-right-left). */
export function swings(samples, amp) {
  let n = 0, dir = 0, ext = null;
  for (const v of samples) {
    if (ext === null) { ext = v; continue; }
    if (dir >= 0 && v > ext) { ext = v; if (dir === 0) dir = 1; continue; }
    if (dir <= 0 && v < ext) { ext = v; if (dir === 0) dir = -1; continue; }
    if (Math.abs(v - ext) >= amp) { n++; dir = v > ext ? 1 : -1; ext = v; }
  }
  return n;
}

export function createPerceiver(opts = {}) {
  const k = { ...SENSE, ...opts };
  const held = {};                       // state name → {since, fired, offSince}
  const jaw = [], yaws = [], pitches = [];
  let quietUntil = 0, seenSince = null, lostSince = null, present = false, lastSeen = -Infinity, everLeft = true;

  function hold(name, on, off, t, ms, out) {
    const h = held[name] || (held[name] = { since: null, fired: false, offSince: null });
    if (on) {
      h.offSince = null;
      if (h.since === null) h.since = t;
      if (!h.fired && t - h.since >= ms) { h.fired = true; out.push({ type: name, t }); }
    } else if (h.since !== null && !h.fired && !off) {
      h.since = null;                    // not held long enough and not quite let go: it starts over, unfired
    } else if (h.since !== null && off) {
      if (h.offSince === null) h.offSince = t;
      if (t - h.offSince >= k.releaseMs) { h.since = null; h.fired = false; h.offSince = null; }
    }
    return h;
  }
  const trim = (arr, t, ms) => { while (arr.length && t - arr[0].t > ms) arr.shift(); };

  /**
   * One analysed frame. `faces`: what the detector saw (the nearest one is read); `hearing`: his microphone hears him;
   * `speaking`: the agent's voice is on. → the events this frame completed.
   */
  function feed({ faces = [], hearing = false, speaking = false } = {}, t) {
    const out = [];
    const f = faces.length ? faces.reduce((a, b) => ((b.size || 0) > (a.size || 0) ? b : a)) : null;

    // ---- presence: a face held for a moment after a long absence is an arrival; a face gone for a while left
    if (f) {
      lastSeen = t; lostSince = null;
      if (seenSince === null) seenSince = t;
      if (!present && t - seenSince >= k.arriveMs) { present = true; if (everLeft) out.push({ type: "arrive", t }); everLeft = false; }
    } else {
      seenSince = null;
      if (lostSince === null) lostSince = t;
      if (present && t - lostSince >= k.awayMs) { present = false; out.push({ type: "leave", t }); }
      if (!present && t - lastSeen >= k.absentMs) everLeft = true;
    }
    if (!f || !f.shapes) return out;
    const sh = f.shapes;

    // ---- talking, seen: the jaw flutters at speech rate (works with the mic muted too)
    const jo = S(sh, "jawOpen");
    jaw.push({ t, v: jo }); trim(jaw, t, k.talkWindowMs);
    const talkingSeen = swings(jaw.map((s) => s.v), k.talkAmp) >= k.talkSwings;
    if (hearing || talkingSeen) quietUntil = t + k.quietMs;
    // a held face also needs a STILL jaw right now: talking is recognised a few swings in, and a quick smile must not
    // slip through in those first frames of speech
    const recent = jaw.filter((x) => t - x.t <= 600).map((x) => x.v);
    const mouthFree = t >= quietUntil && swings(recent, k.talkAmp) <= 1;

    const smile = (S(sh, "mouthSmileLeft") + S(sh, "mouthSmileRight")) / 2;
    const bl = S(sh, "eyeBlinkLeft"), br = S(sh, "eyeBlinkRight");
    const browUp = Math.max(S(sh, "browInnerUp"), (S(sh, "browOuterUpLeft") + S(sh, "browOuterUpRight")) / 2);

    // a laugh: a big smile with the mouth open — allowed while he makes sound (laughing is audible), never while talking
    const g = k.letGo, tongue = S(sh, "tongueOut");
    const laugh = hold("laugh", smile >= k.laughSmile && jo >= k.laughJaw && !(talkingSeen && smile < k.laughSmile + 0.1),
      smile < k.laughSmile * g || jo < k.laughJaw * g, t, k.laughMs, out);
    hold("smile", mouthFree && smile >= k.smile && !laugh.since, smile < k.smile * g, t, k.smileMs, out);
    hold("tongue", mouthFree && tongue >= k.tongue, tongue < k.tongue * g, t, k.tongueMs, out);
    hold("yawn", mouthFree && jo >= k.yawnJaw && smile < 0.3, jo < k.yawnJaw * g, t, k.yawnMs, out);
    hold("surprise", mouthFree && jo >= k.ohJaw && browUp >= k.ohBrow && smile < 0.3, jo < k.ohJaw * g || browUp < k.ohBrow * g,
      t, k.ohMs, out);
    hold("brows", browUp >= k.brows && jo < k.ohJaw, browUp < k.brows * g, t, k.browsMs, out);

    // a wink: ONE eye shut, the other open, for longer than a blink and shorter than a long close
    const side = bl - br >= k.winkGap && bl >= k.winkClosed && br <= k.winkOpen ? "left"
      : br - bl >= k.winkGap && br >= k.winkClosed && bl <= k.winkOpen ? "right" : null;
    const w = held.wink || (held.wink = { since: null, side: null, offSince: null });
    if (side && (w.since === null || w.side === side)) { if (w.since === null) { w.since = t; w.side = side; } w.offSince = null; }
    else if (w.since !== null) {
      const dur = t - w.since;
      if (dur >= k.winkMs && dur <= k.winkMaxMs && w.side) out.push({ type: "wink", t, side: w.side });
      w.since = null; w.side = null;
    }

    // ---- nod / shake from the head pose: two or more swings on one axis, little on the other
    if (f.pose) {
      yaws.push({ t, v: f.pose.yaw }); pitches.push({ t, v: f.pose.pitch });
      trim(yaws, t, k.nodWindowMs); trim(pitches, t, k.nodWindowMs);
      const ny = swings(yaws.map((s) => s.v), k.shakeAmp), np = swings(pitches.map((s) => s.v), k.nodAmp);
      if (np >= 2 && ny === 0) { out.push({ type: "nod", t }); pitches.length = 0; yaws.length = 0; }
      else if (ny >= k.shakeSwings && np <= 1) { out.push({ type: "shake", t }); pitches.length = 0; yaws.length = 0; }
    }
    return out;
  }

  return { feed, get present() { return present; } };
}
