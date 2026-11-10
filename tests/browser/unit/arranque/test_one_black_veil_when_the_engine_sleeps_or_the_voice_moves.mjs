// ============================================================================
// test_one_black_veil_when_the_engine_sleeps_or_the_voice_moves.mjs — 2026-11-10.
//
// The engine's goodnight darkens the whole screen with a Reactivate button; the button (or any gesture) wakes the
// tab, the veil says it is waiting until the stream answers, and lifts when it does. A visible, connected, awake tab
// tells the engine a person is there; a hidden or sleeping one never does.
//
// Run: node tests/browser/unit/arranque/test_one_black_veil_when_the_engine_sleeps_or_the_voice_moves.mjs
// ============================================================================
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const listeners = {};
const timers = [];
globalThis.window = { addEventListener: (ev, fn) => { (listeners[ev] ||= []).push(fn); } };
const docListeners = {};
const pill = { style: {}, setAttribute() {}, textContent: "" };
globalThis.document = { hidden: false, getElementById: () => null, createElement: () => pill, body: { appendChild() {} },
                        addEventListener: (ev, fn) => { (docListeners[ev] ||= []).push(fn); } };
globalThis.setInterval = () => 0;
globalThis.setTimeout = (fn, ms) => { timers.push({ fn, ms }); return timers.length; };
globalThis.clearTimeout = () => {};

const P = await import("../../../../frontend/app/services/presence.js?v=1");

// ── 1. the pure pieces ───────────────────────────────────────────────────────────────────────────────────────────
assert.equal(P.beatDue({ visible: true, open: true, asleep: false }), true);
assert.equal(P.beatDue({ visible: false, open: true, asleep: false }), false, "a hidden tab is nobody");
assert.equal(P.beatDue({ visible: true, open: false, asleep: false }), false, "no stream: nothing to keep up");
assert.equal(P.beatDue({ visible: true, open: true, asleep: true }), false, "a sleeping tab sends nothing");

// `dormantFace` lives in a component that imports the whole shell; its body is pure, so it is read from the source.
const src = readFileSync(new URL("../../../../frontend/app/components/DormantVeil.js", import.meta.url), "utf8");
const body = src.match(/export function dormantFace\(([^)]*)\) \{([\s\S]*?)\n\}/);
assert.ok(body, "dormantFace is exported from DormantVeil.js");
const dormantFace = new Function(...body[1].split(",").map((a) => a.trim()), body[2]);
assert.equal(dormantFace({ face: "sleep" }, false, false, false), "sleep");
assert.equal(dormantFace({ face: "sleep" }, true, false, false), "sleep", "a sleeping engine has no voice anywhere");
assert.equal(dormantFace({ face: "" }, true, false, false), "moved");
assert.equal(dormantFace({ face: "" }, true, true, false), "", "a stopped agent has its own veil");
assert.equal(dormantFace({ face: "" }, true, false, true), "", "«continue here with text» lifts it");
assert.equal(dormantFace({ face: "" }, false, false, false), "");

// ── 2. the wiring ────────────────────────────────────────────────────────────────────────────────────────────────
let opens = 0, wakes = 0, beats = 0;
const seen = [];
P.wirePresence({ open: (o) => { opens++; if (o && o.wake) wakes++; }, close() {}, t: (k) => k,
                 beat: () => beats++, dormant: (d) => seen.push(d) });
const last = () => seen[seen.length - 1];

P.onStreamOpen();
assert.equal(beats, 1, "a page that opened its stream says a person is here at once — within seconds, not a minute");
document.hidden = true; docListeners.visibilitychange[0]();
assert.equal(beats, 1, "a hidden tab never beats");
document.hidden = false; docListeners.visibilitychange[0]();
assert.equal(beats, 2, "becoming visible with the stream open is presence again");

P.presenceEvent({ kind: "session", label: "engine.sleep" });
assert.deepEqual(last(), { face: "sleep", waking: false }, "the engine's goodnight darkens the screen");
assert.equal(pill.textContent, "", "…with the veil, not the orb's pill");
docListeners.visibilitychange[0]();
assert.equal(beats, 2, "a sleeping tab never beats");

P.reactivate();
assert.equal(P.asleep(), false);
assert.equal(wakes, 1, "Reactivate reopens the stream as a person (`wake=1`): the edge wakes the engine for it");
assert.deepEqual(last(), { face: "sleep", waking: true }, "the veil stays and says it is waiting");

P.onStreamError();                                   // the engine is still coming up: the edge answered 503
assert.equal(timers.length, 1, "it retries while he is here");
assert.deepEqual(last(), { face: "sleep", waking: true }, "…and keeps saying it is waiting");
timers.shift().fn();
assert.equal(wakes, 2, "every retry is a person too");

P.onStreamOpen();
assert.deepEqual(last(), { face: "", waking: false }, "the engine answered: the veil lifts");
assert.equal(beats, 3, "…and the woken tab is presence at once");

// a wake that gives up goes back to the veil it came from, never to a dark screen with nothing to press
P.presenceEvent({ kind: "session", label: "engine.sleep" });
P.reactivate();
document.hidden = true;
P.onStreamError();
assert.equal(P.asleep(), true);
assert.deepEqual(last(), { face: "sleep", waking: false }, "a hidden tab stops waiting and shows Reactivate again");
document.hidden = false;
listeners.pointerdown[0]();
assert.deepEqual(last(), { face: "sleep", waking: true }, "any gesture is a Reactivate");

console.log("ok — one black veil when the engine sleeps, lifted when it answers");
