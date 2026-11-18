// mouth.mjs — drives the PARKED speaking mouth (V2-928, mouth.js) in node, directly: a viseme → its nine channels →
// the articulated opening and what would be drawn inside it. Nothing in the live face imports it (the operator preferred
// the simpler mouth, 2026-11-18); this keeps it working for the day it is wired back. argv[2] = the presence folder.
const base = new URL("file://" + process.argv[2].replace(/\/?$/, "/"));
const imp = (f) => import(new URL(f, base).href);
const { mouthFrom, articulatedMouth, drawMouthInside, INSIDE_COLOURS } = await imp("mouth.js?v=1");
const fills = [];
const ctx = new Proxy({}, { get(t, k) { if (k in t) return t[k]; if (k === "fill") return () => fills.push(t.fillStyle); return () => {}; },
  set(t, k, v) { t[k] = v; return true; } });
const V = ["PP", "FF", "TH", "DD", "kk", "CH", "SS", "nn", "RR", "aa", "E", "I", "O", "U"];
const out = {};
for (const v of [null, ...V]) {
  const c = mouthFrom(v ? { [v]: v === "PP" || v === "FF" ? 0.9 : 0.78 } : {});
  const r = { ...c, smile: 0, roll: 0 }, m = articulatedMouth(r);
  const G = { r, mouth: () => m, P: ([x, y]) => ({ x: 50 + x * 30, y: 50 - y * 30, s: 30 }) };
  fills.length = 0; drawMouthInside(ctx, G);
  out[v || "rest"] = { h: m.h, mw: m.mw, open: r.open, press: r.press, bite: r.bite, tip: r.tip, round: r.round, teeth: fills.includes(INSIDE_COLOURS.teeth) };
}
const vec = (k) => [out[k].h * 10, out[k].mw * 5, out[k].bite, out[k].tip, out[k].round, out[k].press];
let minGap = 9, closest = "";
for (let i = 0; i < V.length; i++) for (let j = i + 1; j < V.length; j++) {
  const d = Math.hypot(...vec(V[i]).map((x, k) => x - vec(V[j])[k]));
  if (d < minGap) { minGap = d; closest = V[i] + "/" + V[j]; }
}
const restSame = Math.abs(out.rest.h - 0.012) < 1e-12 && Math.abs(out.rest.mw - 0.2) < 1e-12;
console.log(JSON.stringify({ out, restSame, minGap, closest }));
