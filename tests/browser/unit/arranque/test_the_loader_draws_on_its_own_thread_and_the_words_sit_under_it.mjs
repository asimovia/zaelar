// ============================================================================
// test_the_loader_draws_on_its_own_thread_and_the_words_sit_under_it.mjs
//
// The loader's animation must be able to run where there is NO page: no window, no document, no layout — a worker.
// Everything it needs comes in as `env`. And on every screen the brain lives above the band the words use.
//
// Run: node tests/browser/unit/arranque/test_the_loader_draws_on_its_own_thread_and_the_words_sit_under_it.mjs
// ============================================================================
import assert from "node:assert/strict";

assert.equal(typeof globalThis.window, "undefined", "this test runs with no page at all");
assert.equal(typeof globalThis.document, "undefined");
const A = await import("../../../../frontend/app/components/boot-anim.js?v=5");

// ── where the brain sits ──
const phone = A.placement(390, 844), desk = A.placement(1280, 800);
assert.equal(phone.portrait, true);
assert.equal(phone.band, A.CAPTION_BAND, "upright: a band at the foot is kept for the words");
assert.ok(phone.cy < (844 - A.CAPTION_BAND) * 0.55 && phone.cy > (844 - A.CAPTION_BAND) * 0.45, "the brain is centred in the screen ABOVE the band");
assert.equal(desk.portrait, false);
assert.equal(desk.band, A.CAPTION_BAND, "a wide screen keeps the same band: the words go under the drawing everywhere");
assert.equal(desk.cy, (800 - A.CAPTION_BAND) * 0.5, "…and the brain is centred in the screen above it");

// ── it runs with nothing but its env ──
const calls = { frames: 0, fills: 0, maxY: 0 };
const grad = { addColorStop() {} };
const ctx = new Proxy({}, { get(_t, k) {
  if (k === "createRadialGradient") return (x, y) => { calls.maxY = Math.max(calls.maxY, y); return grad; };
  if (k === "arc") return (x, y, r) => { calls.maxY = Math.max(calls.maxY, y + r); };
  if (k === "fillRect") return () => { calls.fills++; };
  return () => {};
}, set() { return true; } });
const canvas = { width: 0, height: 0, getContext: () => ctx };
let frame = null, resized = null, offCalled = false, now = 0, progress = [];
const env = { reduced: false, colors: { accent: [61, 111, 224], accent2: [139, 92, 246], bg: [13, 22, 34] },
              size: () => ({ w: 390, h: 844, dpr: 2 }),
              onResize: (fn) => { resized = fn; return () => { offCalled = true; }; },
              raf: (fn) => { frame = fn; return 1; }, caf: () => { frame = null; } };
const ctrl = A.startBootAnim(canvas, { onProgress: (p) => progress.push(p), env });
assert.equal(canvas.width, 780, "it sized the canvas from the env, not from a layout it does not have");
for (let i = 0; i < 600 && frame; i++) { now += 16; const f = frame; frame = null; f(now); calls.frames++; }
assert.ok(calls.frames === 600, "it kept drawing on the clock it was given");
assert.ok(ctrl.shown() > 0.3, `the brain grew on its own, with no phase and no page: ${ctrl.shown()}`);
assert.ok(progress.length > 5, "…and reported its progress");
assert.ok(calls.maxY <= 844 - A.CAPTION_BAND + 2, `nothing is drawn inside the words' band: lowest ${calls.maxY} vs ${844 - A.CAPTION_BAND}`);
assert.equal(typeof resized, "function", "a new size reaches it through the env");
ctrl.destroy();
assert.equal(offCalled, true);

// …and the same on a wide screen: nothing is drawn inside the band there either
calls.maxY = 0; frame = null; now = 0;
const wide = A.startBootAnim({ width: 0, height: 0, getContext: () => ctx }, { env: { ...env, size: () => ({ w: 1280, h: 800, dpr: 1 }) } });
for (let i = 0; i < 600 && frame; i++) { now += 16; const f = frame; frame = null; f(now); }
assert.ok(calls.maxY <= 800 - A.CAPTION_BAND + 2, `a wide screen: lowest ${calls.maxY} vs ${800 - A.CAPTION_BAND}`);
wide.destroy();
console.log("ok");
