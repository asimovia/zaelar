// ============================================================================
// test_a_sleeping_tab_never_reconnects_on_its_own.mjs — V2-872.
//
// An engine with an idle stop ends when nobody uses it, and any request can start it again. An open tab whose
// EventSource reconnects on its own after every stop starts it again and again. Presence is the person: a tab
// reconnects only while visible AND touched recently, with a capped backoff; otherwise it sleeps until a gesture.
//
// Run: node tests/browser/unit/arranque/test_a_sleeping_tab_never_reconnects_on_its_own.mjs
// ============================================================================
import assert from "node:assert/strict";

// A browser just big enough for the wiring: listeners, timers and the orb are fakes the test drives by hand.
const listeners = {};
const timers = [];
globalThis.window = { addEventListener: (ev, fn) => { (listeners[ev] ||= []).push(fn); } };
const orb = { style: { opacity: "" } };
const pill = { style: {}, setAttribute() {}, textContent: "" };
globalThis.document = { hidden: false, getElementById: (id) => (id === "orb" ? orb : null),
                        createElement: () => pill, body: { appendChild() {} } };
globalThis.setInterval = () => 0;
globalThis.setTimeout = (fn, ms) => { timers.push({ fn, ms }); return timers.length; };
globalThis.clearTimeout = () => {};

const P = await import("../../../../frontend/app/services/presence.js?v=1");
const MIN = 60000, NOW = 1_800_000_000_000;

// ── 1. the pure decision ─────────────────────────────────────────────────────────────────────────────────
{
  const here = { visible: true, lastInputMs: NOW - 2 * MIN, nowMs: NOW, asleep: false };
  assert.deepEqual(P.reconnectDecision({ ...here, attempt: 0 }), { reconnect: true, delayMs: 2000 });
  assert.deepEqual(P.reconnectDecision({ ...here, attempt: 3 }), { reconnect: true, delayMs: 16000 });
  assert.deepEqual(P.reconnectDecision({ ...here, attempt: 30 }), { reconnect: true, delayMs: 60000 }, "the backoff is capped");
  assert.equal(P.reconnectDecision({ ...here, visible: false }).reconnect, false, "a hidden tab never reconnects");
  assert.equal(P.reconnectDecision({ ...here, asleep: true }).reconnect, false, "a sleeping tab never reconnects");
  assert.equal(P.reconnectDecision({ ...here, lastInputMs: NOW - 11 * MIN }).reconnect, false,
               "THE BUG: a visible tab nobody touched for tab_sleep_min reconnected and woke the engine");
  assert.equal(P.reconnectDecision({ ...here, lastInputMs: 0 }).reconnect, false, "no input at all is nobody");
  assert.equal(P.reconnectDecision({ ...here, lastInputMs: NOW - 11 * MIN, sleepMin: 0 }).reconnect, true,
               "tab_sleep_min 0 turns the sleep off");
  assert.equal(P.reconnectDecision({ ...here, lastInputMs: NOW - 4 * MIN, sleepMin: 3 }).reconnect, false,
               "the deployment's value is the one that counts");
  assert.equal(P.sleepDue({ lastInputMs: NOW - 10 * MIN, nowMs: NOW }), true);
  assert.equal(P.sleepDue({ lastInputMs: NOW - 9 * MIN, nowMs: NOW }), false);
  assert.equal(P.sleepDue({ lastInputMs: NOW - 99 * MIN, nowMs: NOW, sleepMin: 0 }), false);
}

// ── 2. the wiring: an error with him here retries; `engine.sleep` puts the tab to sleep; a gesture wakes it ──
{
  let opens = 0, closes = 0, wakes = 0;
  P.wirePresence({ open: (o) => { opens++; if (o && o.wake) wakes++; }, close: () => closes++, t: (k) => k });
  assert.ok(listeners.pointerdown && listeners.keydown, "a pointer and a key are input");
  assert.equal(listeners.visibilitychange, undefined, "becoming visible is not a gesture");

  P.onStreamError();                                   // the page was just loaded: that counts as someone opening it
  assert.equal(timers.length, 1, "a visible, just-opened tab retries");
  assert.equal(timers[0].ms, 2000);
  timers.shift().fn();
  assert.equal(opens, 1, "…and the retry reopens the stream");
  assert.equal(wakes, 1, "a retry with him here says it is a person (`wake=1`): the edge may start a stopped engine for it");

  P.presenceEvent({ kind: "session", label: "engine.sleep" });
  assert.equal(P.asleep(), true, "the engine's goodnight puts the tab to sleep");
  assert.equal(closes, 1, "…and closes its stream");
  assert.equal(orb.style.opacity, "0.35", "the orb shows the dormant state");
  assert.equal(pill.textContent, "", "the engine's sleep has the full-screen veil, not the tab's pill");

  P.onStreamError();
  assert.equal(timers.length, 0, "a sleeping tab schedules no reconnect");
  globalThis.document.hidden = true; globalThis.document.hidden = false;
  assert.equal(opens, 1, "visibility alone reopens nothing");

  listeners.pointerdown[0]();
  assert.equal(P.asleep(), false, "the first gesture wakes it");
  P.onStreamOpen();
  assert.equal(opens, 2, "…and reconnects");
  assert.equal(wakes, 2, "…as a person");
  assert.equal(orb.style.opacity, "");
}

// ── 3. a hidden tab that loses its stream goes to sleep, it does not retry ─────────────────────────────────
{
  globalThis.document.hidden = true;
  P.onStreamError();
  assert.equal(timers.length, 0, "a hidden tab never reconnects");
  assert.equal(P.asleep(), true);
  assert.equal(pill.textContent, "orb.asleep", "a tab asleep on its own says so under the orb");
  globalThis.document.hidden = false;
  listeners.keydown[0]();
  assert.equal(P.asleep(), false, "a key is a gesture too");
}

// ── 4. the hello's tab_sleep_min is the deployment's ───────────────────────────────────────────────────────
{
  P.presenceEvent({ kind: "session", label: "SSE", tab_sleep_min: 0 });
  assert.equal(P.asleep(), false);
}

// ── 5. a VISIBLE tab nobody touched is not a person (2026-11-11): it never beats, so it keeps nothing awake ───
{
  const up = { visible: true, open: true, asleep: false, nowMs: NOW };
  assert.equal(P.beatDue({ ...up, lastGestureMs: NOW - 2 * MIN }), true, "a tab he touched two minutes ago beats");
  assert.equal(P.beatDue({ ...up, lastGestureMs: 0 }), false,
               "THE BUG: a tab that only came to the foreground beat, and a hosted engine stayed awake with nobody there");
  assert.equal(P.beatDue({ ...up, lastGestureMs: NOW - 11 * MIN }), false, "a gesture older than tab_sleep_min is gone");
  assert.equal(P.beatDue({ ...up, lastGestureMs: 0, sleepMin: 0 }), true, "no idle stop: any visible tab may beat");
  assert.equal(P.beatDue({ ...up, visible: false, lastGestureMs: NOW }), false);
  assert.equal(P.beatDue({ ...up, asleep: true, lastGestureMs: NOW }), false);
  assert.equal(P.openedByPerson({ navType: "navigate" }), true, "he opened the page");
  assert.equal(P.openedByPerson({ navType: "reload" }), true, "he reloaded it");
  assert.equal(P.openedByPerson({ navType: "reload", wasDiscarded: true }), false, "the browser restored a discarded tab");
  assert.equal(P.openedByPerson({ navType: "back_forward" }), false);
  assert.equal(P.openedByPerson({ navType: "prerender" }), false);
}

// ── 6. a tab that comes back reads the ⏻ from the server, and never pushes its own ──────────────────────────
{
  const mk = (off, cmdAt = 0) => { const s = { off, cmdAt, powerOff: () => s.off, setPowerOff: (v) => { s.off = v; },
                                               powerCmdAt: () => s.cmdAt }; return s; };
  const s1 = mk(true);
  assert.equal(P.reflectRunState({ running: true }, NOW, s1), false);
  assert.equal(s1.off, false, "THE BUG: the tab said «stopped» while the server had the agent on for hours");
  const s2 = mk(false);
  P.reflectRunState({ running: false }, NOW, s2);
  assert.equal(s2.off, true);
  const s3 = mk(true, NOW + 1);
  assert.equal(P.reflectRunState({ running: true }, NOW, s3), null, "a reply asked before his last ⏻ is history");
  assert.equal(s3.off, true);
  assert.equal(P.reflectRunState({}, NOW, mk(true)), null, "no answer changes nothing");
}

console.log("ok — a sleeping tab never reconnects on its own");
