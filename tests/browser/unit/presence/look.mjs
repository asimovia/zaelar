// look.mjs — drives «look at me» (V2-928 T10) in node: fake detections → look.js → the rig. argv[2] = the presence folder.
// Prints one JSON line with what the head and the eyes did. No camera, no DOM: the detector's output is what is faked.
const base = new URL("file://" + process.argv[2].replace(/\/?$/, "/"));
const imp = (f) => import(new URL(f, base).href);
const { createRig } = await imp("rig.js?v=1");
const { createTracker, createHeadTracker, blend, direction } = await imp("look.js?v=1");

let seed = 11; const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
const FRAME = 1000 / 60, DET = 80;   // the face draws at 60 fps; the detector answers every 80 ms (12.5 fps)

// Run `secs` seconds; `faceAt(t)` → a detection {x, y, size, q} in the RAW camera frame, or null for nobody.
function run(rig, tracker, secs, faceAt, t0) {
  const out = { yaw: [], gazeX: [], pitch: [], w: [] };
  let t = t0;
  for (let i = 0; i < secs * 60; i++) {
    t += FRAME;
    if (i % Math.round(DET / FRAME) === 0) { const d = faceAt(t); tracker.feed(d ? [d] : [], t); }
    rig.setLook(blend(tracker.sample(t), null));
    const r = rig.update(FRAME, { visemes: {}, mode: "listening" });
    out.yaw.push(r.yaw); out.gazeX.push(r.gazeX); out.pitch.push(r.pitch); out.w.push(rig.lookWeight);
  }
  return { out, t };
}
const tail = (a, n = 60) => a.slice(-n).reduce((s, v) => s + v, 0) / Math.min(n, a.length);
const spread = (a) => Math.max(...a) - Math.min(...a);

const rig = createRig(rnd), tr = createTracker();
// The person stands to THEIR left: the camera looks back at them, so they appear on the frame's RIGHT (x = 0.8).
let s = run(rig, tr, 3, () => ({ x: 0.8, y: 0.45, size: 0.25, q: 60 }), 0);
const left = { yaw: tail(s.out.yaw), gazeX: tail(s.out.gazeX), w: tail(s.out.w) };
// They walk to their right (frame x = 0.2).
s = run(rig, tr, 3, () => ({ x: 0.2, y: 0.45, size: 0.25, q: 60 }), s.t);
const right = { yaw: tail(s.out.yaw), gazeX: tail(s.out.gazeX), w: tail(s.out.w) };
// They stand still while the detector jitters by ±2 % of the frame: the dead band holds the head.
s = run(rig, tr, 4, (t) => ({ x: 0.2 + 0.02 * Math.sin(t / 37), y: 0.45 + 0.02 * Math.cos(t / 29), size: 0.25, q: 60 }), s.t);
const jitterTarget = (() => { const a = []; let t = s.t; for (let i = 0; i < 30; i++) { t += DET; tr.feed([{ x: 0.2 + (i % 2 ? 0.02 : -0.02), y: 0.45, size: 0.25, q: 60 }], t); a.push(tr.sample(t).x); } return spread(a); })();
// They leave: nobody for 5 s — the weight falls to 0 and the idle life has the head back.
s = run(rig, tr, 5, () => null, s.t + 30 * DET);
const gone = { w: tail(s.out.w, 30), yaw: tail(s.out.yaw, 60) };
// Two people: following the first, a second one crossing behind (smaller) does not steal the gaze.
const tr2 = createTracker(), rig2 = createRig(rnd);
s = run(rig2, tr2, 2, () => ({ x: 0.75, y: 0.45, size: 0.3, q: 60 }), 0);
const stick = run(rig2, { feed: (d, t) => tr2.feed(d.length ? [...d, { x: 0.25, y: 0.4, size: 0.12, q: 70 }] : d, t), sample: (t) => tr2.sample(t) },
  2, () => ({ x: 0.75, y: 0.45, size: 0.3, q: 60 }), s.t);
const stay = { yaw: tail(stick.out.yaw) };

// The geometry: one person at the frame's edges and centre, at a laptop's distance (box = a quarter of the frame).
const at = (x) => { const t = createTracker(); t.feed([{ x, y: 0.45, size: 0.25, q: 60, ar: 0.75 }], 0); return t.sample(0); };
const edge = { theirLeft: at(1), theirRight: at(0), centre: at(0.5), trueYaw: direction({ x: 0, y: 0.45, size: 0.25 }).yaw,
  dist: direction({ x: 0.5, y: 0.45, size: 0.25 }).dist };
// the rig at their far left: the head turns a little, the eyes take the rest
const rigE = createRig(rnd), trE = createTracker();
const e = run(rigE, trE, 3, () => ({ x: 1, y: 0.45, size: 0.25, q: 60 }), 0);
const edgeRig = { yaw: tail(e.out.yaw), gazeX: tail(e.out.gazeX) };

// The headphones: he turns his head 0.3 rad to his right from where he faced at the start, then back.
const hd = createHeadTracker(); let ht = 0; const hs = [];
for (let i = 0; i < 50; i++) { ht += 40; hd.feed({ yaw: 1.0, pitch: 0 }, ht); }               // the zero: 1.0 rad
for (let i = 0; i < 50; i++) { ht += 40; hd.feed({ yaw: 1.3, pitch: 0.1 }, ht); hs.push(hd.sample(ht)); }
const headRight = hs[hs.length - 1];
// across the sensor's ±π seam: from 3.1 to -3.1 is a small turn to the right (+0.08), not a whole one
const seam = createHeadTracker(); seam.feed({ yaw: 3.1, pitch: 0 }, 0); seam.feed({ yaw: -3.1, pitch: 0 }, 40);
const seamX = seam.sample(40).x;

// The app's bridge hands Core Motion's attitude as it comes (yaw > 0 = the head turns to ITS left): flipped once.
globalThis.window = { ZaelarNative: { headMotion: { available: async () => true, stop: async () => {},
  start: async (cb) => { cb({ yaw: 0.3, pitch: 0.1, t: 1 }); return true; } } } };
const hm = await imp("head-motion.js?v=1"); let got = null;
const avail = await hm.available(); (await hm.start((m) => { got = m; }))();
const bridgeYaw = got && got.yaw, bridgePitch = got && got.pitch;

console.log(JSON.stringify({ edge, edgeRig, left, right, jitterTarget, gone, stay, headRight, seamX, bridgeYaw, bridgePitch, avail }));
