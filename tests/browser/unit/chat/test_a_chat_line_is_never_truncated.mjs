// ============================================================================
// test_a_chat_line_is_never_truncated.mjs — V2-852 T12, node 4.371.
//
// Measured in the operator's session (2026-11-05): the voice said «You're right on both — …» and the wall kept
// «You're right on» (his ERROR 3); «I'll start it now — a wide» was cut by a barge-in and nothing said so. Two shapes:
//   1. The voice stopped mid-sentence (a barge-in, or simply going quiet) and the crawl stayed on screen showing what
//      had been heard so far — a sentence silently shortened, with no mark.
//   2. The next reply settled the line early, cutting it to what had been heard; when the spoken record came back with
//      the WHOLE sentence it was compared with the cut text («…» and all), matched nothing and was thrown away.
//
// The rules: a line cut mid-sentence is marked cut («…»), never silently shortened; the spoken record writes its row
// from what was voiced, compared with what was owed — whole when the voice said it all, marked cut when it stopped.
//
// Drives the REAL old-path writer (`services/wall-legacy.js`) on the REAL wall model, through `wallkit.mjs`.
//
// M5 (the wall plan, commit 3/5): a FINAL line of ours only shortens — its text never changes and what it shows never
// grows. So a line already settled cut stays cut when a later record says more: the record is refused at the model's
// door («final_grows») and counted, never silently. The early settle that shape 2 measured is narrower now: a line
// is settled only when the voice demonstrably moved on (its next line started, the turn was cut, or the voice went
// idle and its grace ran out), never because the next reply ARRIVED.
//
// Run: node tests/browser/unit/chat/test_a_chat_line_is_never_truncated.mjs
// ============================================================================
import assert from "node:assert/strict";
import { wall } from "./wallkit.mjs";

const rows = (w) => w.said().filter((l) => l.role === "agent").map((l) => l.text);
const crawl = (w) => { const l = w.lines().find((x) => x.role === "agent" && x.state === "live"); return l ? { trace: l.data.trace, said: w.said().find((s) => s.state === "live" && s.role === "agent").text } : null; };
const grew = (w) => w.rejected.filter((r) => r.reason === "final_grows").length;

const CASES = [
  { lang: "en", t1: "T24·c533", t2: "T25·61ee",
    line: "You're right on both — that wasn't meant for me, and nothing should have stopped.",
    heard: "You're right on", next: "Noted — that truncation is a real bug." },
  { lang: "es", t1: "T8·41aa", t2: "T9·52bb",
    line: "Tienes razón en las dos cosas: eso no iba conmigo y no debía pararse nada.",
    heard: "Tienes razón en", next: "Anotado: ese corte es un fallo de verdad." },
];

for (const c of CASES) {
  // ── 1 · a barge-in cuts it mid-sentence: the line is marked cut, the crawl does not stay ───────────────────
  let w = await wall();
  w.legacy.pushAgentChat(c.line, { voiced: true, trace: c.t1 });
  w.legacy.noteVoiceStarted(c.t1);
  w.legacy.noteSpokenAloud(c.heard, false);
  assert.equal(crawl(w).said, c.heard, `[${c.lang}] while it is said, the wall says what was heard`);
  w.legacy.dropUnspokenLine("");                            // `state interrupted`, no trace (as measured)
  assert.equal(crawl(w), null, `[${c.lang}] the crawl ended: a cut sentence is not left on screen as it stood`);
  assert.deepEqual(rows(w), [c.heard + "…"], `[${c.lang}] cut mid-sentence → marked cut, never silently shortened`);
  // …a spoken record with all of it does not lengthen a settled line (M5): refused at the door, and counted
  w.legacy.pushAgentChat(c.line, { spoken: true, trace: c.t1 });
  assert.deepEqual(rows(w), [c.heard + "…"], `[${c.lang}] M5: a final line of ours never grows back`);
  assert.equal(grew(w), 1, `[${c.lang}] …and the refused record is counted, not lost silently`);
  assert.equal(w.lines().filter((l) => l.role === "agent").length, 1, `[${c.lang}] …nor written as a second bubble`);

  // ── 2 · the next reply arrives while this one is still being said: it WAITS, nothing is cut (2026-11-06) ──
  w = await wall();
  w.legacy.pushAgentChat(c.line, { voiced: true, trace: c.t1 });
  w.legacy.noteVoiceStarted(c.t1);
  w.legacy.noteSpokenAloud(c.heard, false);
  w.legacy.pushAgentChat(c.next, { voiced: true, trace: c.t2 });   // owed behind the line still sounding
  assert.deepEqual(rows(w), [c.heard], `[${c.lang}] a reply in progress is not cut by the next one`);
  assert.equal(crawl(w).trace, c.t1, `[${c.lang}] the crawl is still the line being said`);
  w.legacy.noteSpokenAloud(c.line, true);                   // the voice finished it
  assert.deepEqual(rows(w), [c.line], `[${c.lang}] said whole`);
  w.legacy.noteVoiceStarted(c.t2);                          // now the voice says the next one
  assert.deepEqual(rows(w), [c.line, c.next], `[${c.lang}] the waiting line is written when ITS voice starts`);
  // …and when the voice skips straight to the next line, the first ends where the voice left it
  w = await wall();
  w.legacy.pushAgentChat(c.line, { voiced: true, trace: c.t1 });
  w.legacy.noteVoiceStarted(c.t1);
  w.legacy.noteSpokenAloud(c.heard, false);
  w.legacy.pushAgentChat(c.next, { voiced: true, trace: c.t2 });
  w.legacy.noteVoiceStarted(c.t2);
  assert.deepEqual(rows(w), [c.heard + "…", c.next], `[${c.lang}] the voice moved on: the first is marked cut`);
  // M5: the late record of the whole first line does not lengthen it, and never moves or duplicates a row
  w.legacy.pushAgentChat(c.line, { spoken: true, trace: c.t1 });
  assert.deepEqual(rows(w), [c.heard + "…", c.next], `[${c.lang}] M5: a settled line keeps what it showed`);
  assert.equal(grew(w), 1, `[${c.lang}] …and the refused record is counted`);
  // a spoken record of a line that waited is written in its place, once
  w = await wall();
  w.legacy.pushAgentChat(c.line, { voiced: true, trace: c.t1 });
  w.legacy.noteVoiceStarted(c.t1);
  w.legacy.noteSpokenAloud(c.heard, false);
  w.legacy.pushAgentChat(c.next, { voiced: true, trace: c.t2 });
  w.legacy.noteSpokenAloud(c.line, true);
  w.legacy.pushAgentChat(c.next, { spoken: true, trace: c.t2 });
  assert.deepEqual(rows(w), [c.line, c.next], `[${c.lang}] the record of a waiting line writes it`);
  assert.equal(w.rejected.length, 0, `[${c.lang}] ${JSON.stringify(w.rejected)}`);

  // ── 3 · the record itself stops short: written as said, marked cut ────────────────────────────────────────
  w = await wall();
  w.legacy.pushAgentChat(c.line, { voiced: true, trace: c.t1 });
  w.legacy.noteVoiceStarted(c.t1);
  w.legacy.pushAgentChat(c.heard, { spoken: true, trace: c.t1 });
  assert.deepEqual(rows(w), [c.heard + "…"], `[${c.lang}] the voice was cut there: the line says so`);

  // ── 4 · the voice goes quiet mid-line: the crawl never stays a shortened sentence ─────────────────────────
  // `noteVoiceIdle` settles after its grace (IDLE_GRACE_MS): its last caption may land just after the idle.
  w = await wall();
  w.legacy.pushAgentChat(c.line, { voiced: true, trace: c.t1 });
  w.legacy.noteVoiceStarted(c.t1);
  w.legacy.noteSpokenAloud(c.heard, false);
  w.legacy.noteVoiceIdle();
  assert.equal(crawl(w).said, c.heard, `[${c.lang}] within the grace the line still waits for its last caption`);
  w.flush();
  assert.equal(crawl(w), null);
  assert.deepEqual(rows(w), [c.heard + "…"], `[${c.lang}] quiet mid-line → marked cut`);
  // with no caption channel at all, the line it started stays whole
  w = await wall();
  w.legacy.pushAgentChat(c.line, { voiced: true, trace: c.t1 });
  w.legacy.noteVoiceStarted(c.t1);
  w.legacy.noteVoiceIdle();
  w.flush();
  assert.deepEqual(rows(w), [c.line], `[${c.lang}] a silent caption channel is no statement about the voice`);
  assert.equal(crawl(w), null, `[${c.lang}] …and it settled`);
}

console.log("ok — a chat line is never truncated");
