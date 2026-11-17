// humanity.mjs — drives «the face answers you» (V2-928 T12) in node: fake blendshape frames → perceive.js → events,
// events → temperament.js (seeded) → answers → expression.js → the rig. argv[2] = the presence folder.
// Prints one JSON line. No camera, no DOM, no model: the detector's numbers are what is faked.
const base = new URL("file://" + process.argv[2].replace(/\/?$/, "/"));
const imp = (f) => import(new URL(f, base).href);
const { createPerceiver } = await imp("humanity/perceive.js?v=1");
const { createTemperament, seeded, ANSWERS } = await imp("humanity/temperament.js?v=1");
const { createExpression } = await imp("humanity/expression.js?v=1");
const { createRemarker } = await imp("humanity/remark.js?v=1");
const { createHumanity } = await imp("humanity/index.js?v=1");
const { createRig } = await imp("rig.js?v=1");

const DT = 100;                                   // the landmarker's 10 frames a second
const face = (shapes = {}, pose = { yaw: 0, pitch: 0 }) => ({ size: 0.25, shapes, pose });
/** Feed `secs` of frames from `at(t)` (→ a face or null), with `speech` {hearing, speaking}; → the event types. */
function drive(p, secs, at, speech = {}, t0 = 0) {
  const evs = [];
  for (let t = t0; t < t0 + secs * 1000; t += DT) { const f = at(t); for (const e of p.feed({ faces: f ? [f] : [], ...speech }, t)) evs.push(e); }
  return evs;
}
const types = (evs) => evs.map((e) => e.type + (e.side ? ":" + e.side : ""));
const fresh = () => { const p = createPerceiver(); drive(p, 1.2, () => face()); return p; };   // already present, neutral
const flutter = (t) => 0.05 + (Math.floor(t / DT) % 2 ? 0.25 : 0);                           // a talking jaw

const SMILE = { mouthSmileLeft: 0.75, mouthSmileRight: 0.7 };
const perceive = {
  smile: types(drive(fresh(), 1, () => face(SMILE), {}, 2000)),
  smileHearing: types(drive(fresh(), 1, () => face(SMILE), { hearing: true }, 2000)),
  smileTalkingMuted: types(drive(fresh(), 2, (t) => face({ ...SMILE, mouthSmileLeft: 0.6, mouthSmileRight: 0.58, jawOpen: flutter(t) }), {}, 2000)),
  laughHearing: types(drive(fresh(), 1, () => face({ mouthSmileLeft: 0.85, mouthSmileRight: 0.85, jawOpen: 0.4 }), { hearing: true }, 2000)),
  winkLeft: types(drive(fresh(), 0.8, (t) => face(t < 2400 ? { eyeBlinkLeft: 0.7, eyeBlinkRight: 0.08 } : {}), {}, 2000)),
  winkReal: types(drive(fresh(), 0.8, (t) => face(t < 2300 ? { eyeBlinkLeft: 0.48, eyeBlinkRight: 0.3 } : { eyeBlinkLeft: 0.12, eyeBlinkRight: 0.1 }), {}, 2000)),
  blinkBoth: types(drive(fresh(), 0.8, (t) => face(t < 2300 ? { eyeBlinkLeft: 0.7, eyeBlinkRight: 0.7 } : {}), {}, 2000)),
  eyeShutLong: types(drive(fresh(), 3, (t) => face(t < 4500 ? { eyeBlinkLeft: 0.7, eyeBlinkRight: 0.08 } : {}), {}, 2000)),
  smileHover: types(drive(fresh(), 6, (t) => face({ mouthSmileLeft: 0.52 + 0.08 * Math.sin(t / 300), mouthSmileRight: 0.52 + 0.08 * Math.sin(t / 300) }), {}, 2000)),
  tongue: types(drive(fresh(), 1, () => face({ tongueOut: 0.5, jawOpen: 0.2 }), {}, 2000)),
  tongueHearing: types(drive(fresh(), 1, () => face({ tongueOut: 0.5, jawOpen: 0.2 }), { hearing: true }, 2000)),
  yawn: types(drive(fresh(), 1.6, () => face({ jawOpen: 0.75 }), {}, 2000)),
  talkingNoYawn: types(drive(fresh(), 3, (t) => face({ jawOpen: flutter(t) + (t % 700 < 300 ? 0.5 : 0) }), {}, 2000)),
  nod: types(drive(fresh(), 1.6, (t) => face({}, { yaw: 0, pitch: 0.05 * Math.sin((t - 2000) / 1000 * Math.PI * 2 * 2) }), {}, 2000)),
  shake: types(drive(fresh(), 1.6, (t) => face({}, { yaw: 0.1 * Math.sin((t - 2000) / 1000 * Math.PI * 2 * 2), pitch: 0 }), {}, 2000)),
  // he turns to look aside and back, and he sways gently: neither is a «no»
  lookAside: types(drive(fresh(), 2, (t) => face({}, { yaw: 0.25 * Math.sin(Math.PI * Math.min(1, (t - 2000) / 1500)), pitch: 0 }), {}, 2000)),
  sway: types(drive(fresh(), 4, (t) => face({}, { yaw: 0.04 * Math.sin((t - 2000) / 1000 * Math.PI * 2 * 1.5), pitch: 0 }), {}, 2000)),
};
// presence: nobody, then someone, then nobody for a while
const pp = createPerceiver();
perceive.presence = types([...drive(pp, 2, () => null), ...drive(pp, 2, () => face(), {}, 2000), ...drive(pp, 6, () => null, {}, 4000)]);

// ---- temperament: seeded, so a test can hold it to the letter
const answersFor = (seed, evs, speaking = false) => { const tp = createTemperament({ rng: seeded(seed) });
  return evs.map((e) => { const a = tp.hear(e, e.t, { speaking }); return a ? a.answer : null; }); };
const winks = Array.from({ length: 1 }, () => ({ type: "wink", side: "left", t: 0 }));
const many = (n, type) => Array.from({ length: n }, (_, i) => ({ type, t: i * 4000 }));
const temper = {
  sameSeedSame: JSON.stringify(answersFor(5, many(8, "smile"))) === JSON.stringify(answersFor(5, many(8, "smile"))),
  winkAcross: (() => { const c = {}; for (let s = 1; s <= 300; s++) { const a = answersFor(s, winks)[0] ?? "nothing"; c[a] = (c[a] || 0) + 1; } return c; })(),
  yawnAcross: (() => { const c = {}; for (let s = 1; s <= 300; s++) { const a = answersFor(s, [{ type: "yawn", t: 0 }])[0] ?? "nothing"; c[a] = (c[a] || 0) + 1; } return c; })(),
  cooldown: (() => { let both = 0; for (let s = 1; s <= 100; s++) { const a = answersFor(s, [{ type: "laugh", t: 0 }, { type: "laugh", t: 500 }]); if (a[0] && a[1]) both++; } return both; })(),
  tired: (() => { const late = new Set(); for (let s = 1; s <= 60; s++) answersFor(s, many(8, "smile")).slice(5).forEach((a) => late.add(a ?? "nothing")); return [...late].sort(); })(),
  speakingMouth: (() => { const seen = new Set(); for (let s = 1; s <= 200; s++) for (const ty of ["laugh", "tongue", "yawn"]) { const a = answersFor(s, [{ type: ty, t: 0 }], true)[0]; if (a) seen.add(a); } return [...seen].sort(); })(),
  sameTwice: (() => { let n = 0; for (let s = 1; s <= 200; s++) { const a = answersFor(s, [{ type: "laugh", t: 0 }, { type: "laugh", t: 2500 }]); if (a[0] && a[0] === a[1]) n++; } return n; })(),
  delays: (() => { const tp = createTemperament({ rng: seeded(3) }); const d = []; for (let i = 0; i < 40; i++) { const a = tp.hear({ type: "arrive", t: i * 3000 }, i * 3000); if (a) d.push(a.delayMs); } return [Math.min(...d), Math.max(...d)]; })(),
  everyEvent: Object.keys(ANSWERS).sort(),
  firstAnswered: (() => { const n = {}; for (const ty of ["smile", "wink", "laugh", "tongue"]) { n[ty] = 0; for (let s = 1; s <= 200; s++) if (answersFor(s, [{ type: ty, t: 0 }])[0]) n[ty]++; } return n; })(),
  repeatLetGo: (() => { let n = 0; for (let s = 1; s <= 200; s++) n += answersFor(s, [{ type: "wink", t: 0 }, { type: "wink", t: 3000 }, { type: "wink", t: 6000 }]).slice(1).filter((a) => !a).length; return n; })(),
};

// ---- expression: a wink mostly mirrors him; a hello is a brow flash and a smile
const played = []; const fakeFace = { gesture: (n) => played.push(n) };
const ex = createExpression(fakeFace, { rng: seeded(9) });
let mirror = 0; for (let i = 0; i < 200; i++) { played.length = 0; ex.play("wink", { side: "left" }); if (played[0] === "winkL") mirror++; }
played.length = 0; ex.play("hello"); const hello = played.slice();

// ---- the seam: one summary per stretch, after 20–60 s of play, never before
const offered = []; const rm = createRemarker({ rng: seeded(4), offer: (s) => offered.push(s) });
for (let t = 0; t <= 90000; t += 3000) rm.note({ type: t % 9000 ? "smile" : "wink" }, t);
const seam = { offers: offered.length, seconds: offered[0] && offered[0].seconds, line: offered[0] && offered[0].line };

// ---- the whole humanity on a fake face: an answer is played after its human beat; his talking mouth gets none
function wholeRun(hearing) {
  const g = []; const timers = [];
  const hm = createHumanity({ gesture: (n) => g.push(n) }, { rng: seeded(21), speech: () => ({ hearing, speaking: false }),
    setTimer: (fn, ms) => { timers.push(fn); return timers.length; }, clearTimer: () => {} });
  for (let t = 0; t < 4000; t += DT) hm.frame([face()], t);
  for (let t = 4000; t < 9000; t += DT) hm.frame([face({ tongueOut: 0.6, jawOpen: 0.25 })], t);
  timers.forEach((fn) => fn());
  return { gestures: g, log: hm.log.map((x) => x.saw + ">" + x.answer) };
}
const whole = { silent: wholeRun(false), hearing: wholeRun(true) };

// ---- the rig plays the new gestures
const at = (name, ms) => { const rig = createRig(seeded(2)); rig.gesture(name); let r; for (let t = 0; t < ms; t += 16) r = rig.update(16, { visemes: {}, mode: "listening" }); return r; };
const rr = { tongue: at("tongue", 800).tongue, yawnOpen: at("yawn", 1300).open };
const wl = at("winkL", 450); rr.winkL = { L: wl.blinkL, R: wl.blinkR };

// ---- the tongue is drawn over EVERY look (the classics and the parametric faces), on top, and only when it is out
const { drawLook, lookOf } = await imp("face.js?v=1");
const { STYLES } = await imp("classics.js?v=1");
const { buildCatalog } = await imp("catalog.js?v=1");
const fills = []; const grad = { addColorStop() {} };
const ctx = new Proxy({}, { get(t, k) { if (k in t) return t[k]; if (/^create.*Gradient|createPattern/.test(k)) return () => grad;
  if (k === "measureText") return () => ({ width: 5 }); if (k === "getImageData") return () => ({ data: new Uint8ClampedArray(4) });
  if (k === "canvas") return { width: 100, height: 100 }; if (k === "fill") return () => fills.push(t.fillStyle); return () => {}; },
  set(t, k, v) { t[k] = v; return true; } });
globalThis.document = { createElement: () => ({ getContext: () => ctx, width: 0, height: 0 }) };
globalThis.OffscreenCanvas = class { getContext() { return ctx; } };
const looks = [...STYLES.map((st) => ({ id: st.id, look: { style: st } })), ...buildCatalog(2).map((f) => ({ id: f.id, look: lookOf(f) }))];
const tongueDrawn = { out: 0, outOf: looks.length, atRest: 0, errors: [] };
const r0 = createRig(seeded(1)).update(16, { visemes: {}, mode: "listening" });
for (const { id, look } of looks) {
  const colour = (look.spec && look.spec.mouth && look.spec.mouth.tongue) || "#e0607a";
  try {
    fills.length = 0; drawLook(ctx, look, { ...r0, tongue: 0.9 }, 50, 50, 30, 100, 100);
    if (fills.length && fills[fills.length - 1] === colour) tongueDrawn.out++;
    fills.length = 0; drawLook(ctx, look, { ...r0, tongue: 0 }, 50, 50, 30, 100, 100);
    if (fills.length && fills[fills.length - 1] === colour && look.style) tongueDrawn.atRest++;
  } catch (e) { tongueDrawn.errors.push(id + ": " + e.message); }
}

console.log(JSON.stringify({ perceive, temper, mirror, hello, seam, whole, rig: rr, tongueDrawn }));
