// ============================================================================
// test_a_phone_back_from_the_background_runs_the_new_screen.mjs — the update channel on the PHONE (node 4.600).
//
// Measured 2026-11-19: a release changed the phone's home; his app, alive in the background since the build before,
// came back to the foreground still running the old screen, because the channel only showed «new version — tap to
// update». On the phone (`reloadOnReturn`) coming back onto a newer frontend reloads at once; the desktop keeps the bar;
// coming back onto the same frontend reloads nothing.
//
// Run: node tests/browser/unit/arranque/test_a_phone_back_from_the_background_runs_the_new_screen.mjs [watch.js URL]
// ============================================================================
import assert from "node:assert/strict";

const listeners = {};
let reloads = 0, rev = "A";
globalThis.window = { addEventListener() {} };
globalThis.document = { visibilityState: "visible", hidden: false,
  addEventListener: (ev, fn) => { (listeners[ev] ||= []).push(fn); },
  getElementById: () => null, createElement: () => ({ style: {}, setAttribute() {} }), body: { appendChild() {} } };
globalThis.location = { reload: () => { reloads++; } };
globalThis.setInterval = () => 0;
globalThis.setTimeout = () => 0;
globalThis.fetch = async () => ({ ok: true, json: async () => ({ build: 1, ui_rev: rev }) });

const url = process.argv[2] || new URL("../../../../frontend/app/update/watch.js", import.meta.url).href;
const W = await import(url);
const comeBack = async () => {
  document.visibilityState = "hidden"; for (const f of listeners.visibilitychange || []) f();
  document.visibilityState = "visible"; for (const f of listeners.visibilitychange || []) f();
  await new Promise((r) => setImmediate(r)); await new Promise((r) => setImmediate(r));
};

W.startUpdateWatch(1e9);
await new Promise((r) => setImmediate(r));                     // the first answer is this page's baseline (A)

// The desktop: a newer frontend shows the bar, nothing reloads by itself.
rev = "B"; await comeBack();
assert.equal(W.stale(), true, "the newer frontend is noticed");
assert.equal(reloads, 0, "the desktop keeps the bar");

// The phone: back from the background onto a newer frontend → reload at once.
W.reloadOnReturn(true);
await comeBack();
assert.equal(reloads, 1, "THE BUG: the phone came back onto a newer frontend and kept running the old screen");

// The same frontend: nothing reloads.
W.__reset(); rev = "C"; await W.check();                      // a fresh baseline (C), as after the reload
reloads = 0; await comeBack();
assert.equal(reloads, 0, "the same frontend never reloads");

console.log("ok — a phone back from the background runs the new screen");
