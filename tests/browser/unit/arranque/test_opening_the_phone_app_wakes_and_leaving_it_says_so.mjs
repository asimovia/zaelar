// ============================================================================
// test_opening_the_phone_app_wakes_and_leaving_it_says_so.mjs — the app on his phone is opened by a person.
//
// Measured by the operator (2026-11-16): he opened the phone app, found the agent asleep and had to press a button to
// wake it — two actions for one. In the app (the native companion, or the page installed on the home screen) coming
// to the foreground IS the gesture: it wakes a sleeping tab, and the tab's `wake=1` wakes a sleeping engine. Leaving
// it is said (`left`), so the engine does not wait its whole window for a phone that was put away. A browser tab
// keeps the rule of 2026-11-11: becoming visible is not a person.
//
// Run: node tests/browser/unit/arranque/test_opening_the_phone_app_wakes_and_leaving_it_says_so.mjs [app|tab]
// ============================================================================
import assert from "node:assert/strict";

const MODE = process.argv[2] || "app";
const listeners = {}, docListeners = {};
globalThis.window = { addEventListener: (ev, fn) => { (listeners[ev] ||= []).push(fn); } };
const orb = { style: { opacity: "" } };
const pill = { style: {}, setAttribute() {}, textContent: "" };
const inApp = MODE === "app";
globalThis.document = { hidden: false, getElementById: (id) => (id === "orb" ? orb : null), createElement: () => pill,
                        body: { appendChild() {} }, documentElement: { classList: { contains: (c) => inApp && c === "in-app" } },
                        addEventListener: (ev, fn) => { (docListeners[ev] ||= []).push(fn); } };
Object.defineProperty(globalThis, "navigator", { value: { standalone: false }, configurable: true });
globalThis.matchMedia = () => ({ matches: MODE === "pwa" });
globalThis.setInterval = () => 0;
globalThis.setTimeout = () => 0;
globalThis.clearTimeout = () => {};

const P = await import("../../../../frontend/app/services/presence.js?v=1");

// ── the pure reading ──
assert.equal(P.installedApp({}), false, "a browser tab");
assert.equal(P.installedApp({ inApp: true }), true, "the native companion");
assert.equal(P.installedApp({ standalone: true }), true, "iOS home-screen app");
assert.equal(P.installedApp({ displayStandalone: true }), true, "an installed page");

let opens = 0, wakes = 0, closes = 0, lefts = 0, beats = 0;
P.wirePresence({ open: (o) => { opens++; if (o && o.wake) wakes++; }, close: () => closes++, t: (k) => k,
                 beat: () => beats++, left: () => lefts++, dormant: () => {} });
const show = (visible) => { globalThis.document.hidden = !visible; for (const fn of docListeners.visibilitychange || []) fn(); };

P.onStreamOpen();
P.presenceEvent({ kind: "session", label: "engine.sleep" });          // the engine said goodnight: the tab sleeps
assert.equal(P.asleep(), true);

show(false);
if (MODE === "tab") {
  assert.equal(lefts, 0, "a browser tab that is hidden says nothing about leaving");
  show(true);
  assert.equal(P.asleep(), true, "a browser tab coming to the foreground is not a person: it stays asleep");
  assert.equal(opens, 0);
  listeners.pointerdown[0]();
  assert.equal(P.asleep(), false, "…his touch wakes it, as before");
} else {
  assert.equal(lefts, 0, "asleep, the app sends nothing — not even that he left");
  show(true);
  assert.equal(P.asleep(), false, "THE BUG: coming back to the phone app wakes it, with nothing to press");
  assert.equal(opens, 1, "…its stream reopens");
  assert.equal(wakes, 1, "…marked as a person (`wake=1`): the edge starts the sleeping engine for it");
  P.onStreamOpen();
  const before = beats;
  show(false);
  assert.equal(lefts, 1, "putting the app away, awake, says the person left");
  assert.equal(beats, before, "…and a hidden app says nobody is present");
  show(true);
  assert.equal(lefts, 1, "coming back is not leaving");
  assert.ok(beats > before, "…and a visible, awake app he just opened says he is here");
}
console.log("ok", MODE);
