// mouth.mjs — drives the speaking mouth (V2-928, mouth.js) in node: a held viseme → the rig → the shared mouth
// geometry and what is drawn inside it. argv[2] = the presence folder. Prints one JSON line.
const base = new URL("file://" + process.argv[2].replace(/\/?$/, "/"));
const imp = (f) => import(new URL(f, base).href);
const { createRig, geometry } = await imp("rig.js?v=1");
const { drawLook } = await imp("face.js?v=1");
const { STYLES } = await imp("classics.js?v=1");
const { INSIDE_COLOURS } = await imp("mouth.js?v=1");
const fills = []; const grad = { addColorStop() {} };
const ctx = new Proxy({}, { get(t, k) { if (k in t) return t[k]; if (/^create.*Gradient|createPattern/.test(k)) return () => grad;
  if (k === "measureText") return () => ({ width: 5 }); if (k === "getImageData") return () => ({ data: new Uint8ClampedArray(4) });
  if (k === "canvas") return { width: 100, height: 100 }; if (k === "fill") return () => fills.push(t.fillStyle); return () => {}; },
  set(t, k, v) { t[k] = v; return true; } });
globalThis.document = { createElement: () => ({ getContext: () => ctx, width: 0, height: 0 }) };
globalThis.OffscreenCanvas = class { getContext() { return ctx; } };

const V = ["PP", "FF", "TH", "DD", "kk", "CH", "SS", "nn", "RR", "aa", "E", "I", "O", "U"];
function held(v) {
  let seed = 3; const rig = createRig(() => ((seed = (seed * 16807) % 2147483647) / 2147483647));
  let r; for (let k = 0; k < 30; k++) r = rig.update(16, { visemes: v ? { [v]: v === "PP" || v === "FF" ? 0.9 : 0.78 } : {}, mode: v ? "speaking" : "listening" });
  return { ...r, smile: 0, yaw: 0, pitch: 0, roll: 0 };
}
const porcelain = { style: STYLES.find((s) => s.id === "porcelain") }, led = { style: STYLES.find((s) => s.id === "led") };
const teethIn = (look, r) => { fills.length = 0; drawLook(ctx, look, r, 50, 50, 30, 100, 100); return fills.includes(INSIDE_COLOURS.teeth); };
const out = {};
for (const v of [null, ...V]) {
  const r = held(v), m = geometry(r, 50, 50, 30).mouth();
  out[v || "rest"] = { h: m.h, mw: m.mw, open: r.open, press: r.press, bite: r.bite, tip: r.tip, round: r.round,
    teeth: teethIn(porcelain, r), ledTeeth: teethIn(led, r) };
}
// at rest the mouth is the one it always was (the old formula, the speech channels all 0)
const r0 = held(null), m0 = geometry(r0, 50, 50, 30).mouth();
const oldH = (0.012 + 0.21 * r0.open) * (1 - r0.press * 0.9), oldMw = 0.2 * (1 + 0.35 * r0.wide - 0.4 * r0.round + 0.15 * Math.max(0, r0.smile));
const restSame = Math.abs(m0.h - oldH) < 1e-9 && Math.abs(m0.mw - oldMw) < 1e-9;
// resolution: every pair of sounds draws a different mouth (height, width and the inner channels)
const vec = (k) => [out[k].h * 10, out[k].mw * 5, out[k].bite, out[k].tip, out[k].round, out[k].press];
let minGap = 9, closest = "";
for (let i = 0; i < V.length; i++) for (let j = i + 1; j < V.length; j++) {
  const d = Math.hypot(...vec(V[i]).map((x, k) => x - vec(V[j])[k]));
  if (d < minGap) { minGap = d; closest = V[i] + "/" + V[j]; }
}
console.log(JSON.stringify({ out, restSame, minGap, closest }));
