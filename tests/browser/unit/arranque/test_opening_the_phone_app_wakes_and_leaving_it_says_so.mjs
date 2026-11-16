// ============================================================================
// test_opening_the_phone_app_wakes_and_leaving_it_says_so.mjs — the app on his phone is opened by a person.
//
// Measured by the operator (2026-11-16): he opened the phone app, found the agent asleep and had to press a button to
// wake it — two actions for one. In the app (the native companion, or the page installed on the home screen) coming
// to the foreground IS the gesture: it wakes a sleeping tab, and the tab's `wake=1` wakes a sleeping engine. Leaving
// it is said (`left`), so the engine does not wait its whole window for a phone that was put away. A browser tab
// keeps the rule of 2026-11-11: becoming visible is not a person.
//
// Run: node tests/browser/unit/arranque/test_opening_the_phone_app_wakes_and_leaving_it_says_so.mjs [app|pwa|tab|desk]
//   app  = the native companion · pwa = installed on a phone's home screen · tab = a browser tab ·
//   desk = a standalone window on a COMPUTER (an installed desktop app): standalone, but not a phone
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
const media = [];
globalThis.document.querySelectorAll = () => media;
globalThis.matchMedia = (q) => ({ matches: /standalone/.test(q) ? (MODE === "pwa" || MODE === "desk") : /coarse/.test(q) ? MODE === "pwa" : false });
globalThis.setInterval = () => 0;
globalThis.setTimeout = () => 0;
globalThis.clearTimeout = () => {};

let clock = 1_800_000_000_000;                       // the test's own clock: time passes when the test says so
Date.now = () => clock;
const later = (ms) => { clock += ms; };

const P = await import("../../../../frontend/app/services/presence.js?v=1");

// ── the pure reading ──
assert.equal(P.installedApp({}), false, "a browser tab");
assert.equal(P.installedApp({ inApp: true }), true, "the native companion");
assert.equal(P.installedApp({ standalone: true }), true, "iOS home-screen app");
assert.equal(P.installedApp({ displayStandalone: true, coarse: true }), true, "a page installed on a phone");
assert.equal(P.installedApp({ displayStandalone: true }), false, "a standalone window on a computer is not a phone");
assert.equal(P.soundingNow([{ paused: true }, { paused: false, ended: true }, { paused: false, muted: true }]), false);
assert.equal(P.soundingNow([{ paused: true }, { paused: false, ended: false, muted: false }]), true, "music is sounding");

// ── the native app leaves its mark for a deployment's edge; a browser tab and a home-screen page do not ──
const jar = (cls) => { const d = { cookie: "", documentElement: { classList: { contains: (c) => cls && c === "in-app" } } }; return d; };
const native = jar(true), plain = jar(false);
assert.equal(P.markNativeApp(native, { protocol: "https:" }), "zaelar_app=1; Path=/; Max-Age=31536000; SameSite=Lax; Secure");
assert.equal(native.cookie, "zaelar_app=1; Path=/; Max-Age=31536000; SameSite=Lax; Secure");
assert.equal(P.markNativeApp(jar(true), { protocol: "http:" }), "zaelar_app=1; Path=/; Max-Age=31536000; SameSite=Lax", "no Secure on a plain-http engine");
assert.equal(P.markNativeApp(plain, { protocol: "https:" }), "", "a browser tab leaves none");
assert.equal(plain.cookie, "");

let opens = 0, wakes = 0, closes = 0, lefts = 0, beats = 0;
P.wirePresence({ open: (o) => { opens++; if (o && o.wake) wakes++; }, close: () => closes++, t: (k) => k,
                 beat: () => beats++, left: () => lefts++, dormant: () => {} });
const show = (visible) => { globalThis.document.hidden = !visible; for (const fn of docListeners.visibilitychange || []) fn(); };

assert.equal(/zaelar_app=1/.test(globalThis.document.cookie || ""), MODE === "app", "wiring presence marks the native app, and only it");
P.onStreamOpen();
later(60000);                                                           // a minute after he opened it…
P.presenceEvent({ kind: "session", label: "engine.sleep" });          // …the engine said goodnight: the tab sleeps
assert.equal(P.asleep(), true);

show(false);
if (MODE === "tab" || MODE === "desk") {
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

  media.push({ paused: false, ended: false, muted: false });           // music the agent started is sounding
  show(false);
  assert.equal(lefts, 1, "putting the phone away with music on is not leaving");
  media.length = 0;
  show(true);

  // the goodnight the engine sent while the page was frozen arrives just after he brought the app to the front
  later(120000); show(false); show(true); later(2000);
  const o = opens;
  P.presenceEvent({ kind: "session", label: "engine.sleep" });
  assert.equal(P.asleep(), false, "he is here: it wakes at once instead of showing a veil to press");
  assert.equal(opens, o + 1, "…and reopens its stream");
}
console.log("ok", MODE);
