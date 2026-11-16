// ============================================================================
// test_the_loader_draws_on_its_own_thread_and_the_words_sit_under_it.mjs
//
// The loader's animation must be able to run where there is NO page: no window, no document, no layout — a worker.
// Everything it needs comes in as `env`. And on a screen held upright the brain lives above the band the words use.
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
assert.equal(desk.band, 0, "landscape keeps none");
assert.equal(desk.cy, 800 * 0.46, "…and the brain stays where it was");

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
console.log("ok");
