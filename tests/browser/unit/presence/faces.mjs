// faces.mjs — drives frontend/app/presence/ in node with a canvas stub (V2-928). argv[2] = the presence folder.
// Prints one JSON line: how many faces drew, the errors, the catalogue ids, and how alive the rig is.
const base = new URL("file://" + process.argv[2].replace(/\/?$/, "/"));
const imp = (f) => import(new URL(f, base).href);
const { CATEGORIES, buildCatalog } = await imp("catalog.js?v=1");
const { drawAvatar, shapeOf } = await imp("creator.js?v=1");
const { STYLES } = await imp("classics.js?v=1");
const { createRig, geometry } = await imp("rig.js?v=1");
const grad = { addColorStop() {} };
const ctx = new Proxy({}, { get(t, k) { if (k in t) return t[k]; if (/^create.*Gradient|createPattern/.test(k)) return () => grad;
  if (k === "measureText") return () => ({ width: 5 }); if (k === "getImageData") return () => ({ data: new Uint8ClampedArray(4) });
  if (k === "canvas") return { width: 100, height: 100 }; return () => {}; }, set(t, k, v) { t[k] = v; return true; } });
globalThis.document = { createElement: () => ({ getContext: () => ctx, width: 0, height: 0 }) };
globalThis.OffscreenCanvas = class { getContext() { return ctx; } };

// 1. every face draws, speaking and at rest
const rig = createRig(); let drawn = 0; const errors = [];
const faces = buildCatalog(14);
for (const [dt, mode] of [[16, "listening"], [400, "speaking"], [2600, "thinking"]]) {
  const r = rig.update(dt, { visemes: { aa: 0.6, O: 0.2 }, mode });
  for (const s of STYLES) { try { s.draw(ctx, geometry(r, 50, 50, 30), 100, 100); drawn++; } catch (e) { errors.push("c-" + s.id + ": " + e.message); } }
  for (const f of faces) { try { drawAvatar(ctx, geometry(r, 50, 50, 30, shapeOf(f.spec)), f.spec); drawn++; } catch (e) { errors.push(f.id + ": " + e.message); } }
}

// 2. alive: a seeded rig, 60 s at rest, then 20 s of speech with bursts of energy
let seed = 7; const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
const still = createRig(rnd), xs = { yaw: [], pitch: [], roll: [], gazeX: [], gazeY: [], brow: [] };
for (let i = 0; i < 60 * 60; i++) { const r = still.update(1000 / 60, { visemes: {}, mode: "listening" }); for (const k in xs) xs[k].push(r[k]); }
const spread = Object.fromEntries(Object.entries(xs).map(([k, v]) => [k, Math.max(...v) - Math.min(...v)]));
let browPeaks = 0, last = 0;
for (let i = 0; i < 20 * 60; i++) {
  const burst = Math.floor(i / 45) % 2 ? 0.9 : 0.15;
  const r = still.update(1000 / 60, { visemes: { aa: burst }, mode: "speaking" });
  if (r.brow - last > 0.02) browPeaks++; last = r.brow;
}
console.log(JSON.stringify({ drawn, errors: errors.slice(0, 5), nErrors: errors.length, styles: STYLES.map((s) => s.id),
  bases: [...new Set(faces.map((f) => f.id.slice(0, f.id.lastIndexOf("-"))))], cats: CATEGORIES.map((c) => c.id), nFaces: faces.length, spread, browPeaks }));
