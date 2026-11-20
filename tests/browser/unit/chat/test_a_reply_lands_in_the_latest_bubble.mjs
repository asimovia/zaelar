// ============================================================================
// test_a_reply_lands_in_the_latest_bubble.mjs — V2-852 T13, node 4.372.
//
// Measured in the operator's session (2026-11-05, his ERROR 6): «you are answering me in the middle of your own reply
// and there is text below it — there is one focus, always write in the last message». The voice was queued: a reply
// owed at one moment was spoken two minutes later, after a proactive notice and another turn's line. An utterance that
// named NO turn (the notice's) was taken as this line's start, so the reply was painted under the notice and then,
// when the other turn's late line arrived, crawled in a bubble ABOVE it.
//
// The rules: a line is placed when ITS voice starts it (its trace, its caption or its spoken record) — append by
// arrival, one focus; a spoken record joins the row of its own turn wherever it is, and never moves a row.
//
// Drives the REAL old-path writer (`services/wall-legacy.js`) on the REAL wall model, through `wallkit.mjs`.
// The wall plan §5.1 (order by start) is this file's rule made general: a line takes its place where its voice STARTS
// it, appended, never inserted by time. M5: a final line of ours only shortens, so a late record of an OLDER line
// that was already settled cut cannot lengthen it — it is refused and counted, and it never adds or moves a row.
//
// Run: node tests/browser/unit/chat/test_a_reply_lands_in_the_latest_bubble.mjs
// ============================================================================
import assert from "node:assert/strict";
import { wall } from "./wallkit.mjs";

const rows = (w) => w.lines().filter((l) => l.role === "agent").map((l) => l.text);    // the rows, in wall order
const said = (w) => w.said().filter((l) => l.role === "agent").map((l) => l.text);     // what each row SHOWS
const crawl = (w) => w.lines().find((l) => l.role === "agent" && l.state === "live") || null;

const CASES = [
  { lang: "en", A: "Checking… it shouldn't have asked, and it won't again — I'm telling it to go on.",
    B: "Yep — one search, but two cards: one is a leftover from the cancelled run.",
    note: "🔔 The search has been running for a while.", ask: "Task 3 needs your OK to click «Clear filters». Shall I?" },
  { lang: "es", A: "Lo miro… no tenía que preguntarte y no lo volverá a hacer: le digo que siga.",
    B: "Sí: una búsqueda y dos apps, una es lo que quedó del intento cancelado.",
    note: "🔔 La búsqueda lleva un rato en marcha.", ask: "La tarea necesita tu permiso para pulsar «Borrar filtros». ¿Lo hago?" },
];
const TA = "T29·88e9", TB = "T27·e2da";

for (const c of CASES) {
  let w = await wall();
  const L = w.legacy;
  L.pushAgentChat(c.B, { voiced: true, trace: TB });        // owed, its voice queued behind another line
  L.pushAgentChat(c.A, { voiced: true, trace: TA });        // the next reply: B was never started, so it is not on screen
  L.pushAgentChat(c.note);                                  // a proactive notice, written at once
  L.pushAgentChat(c.ask, { spoken: true });                 // the voice says a notice — its record names no turn
  L.noteVoiceStarted("");                                   // …the next utterance starts, naming no turn
  assert.deepEqual(said(w), [c.note, c.ask],
    `[${c.lang}] an utterance that names no turn is not this reply's start: nothing is written above what comes next`);
  L.pushAgentChat(c.B, { spoken: true, trace: TB });        // it was B the voice was saying
  L.noteVoiceStarted("");
  L.noteSpokenAloud(c.A.slice(0, 20), false);               // and now A, by its own caption
  assert.deepEqual(rows(w), [c.note, c.ask, c.B, c.A], `[${c.lang}] every line lands in the order it was said`);
  assert.deepEqual(said(w), [c.note, c.ask, c.B, c.A.slice(0, 20)], `[${c.lang}] …and A crawls from its caption`);
  assert.equal(crawl(w).data.trace, TA, `[${c.lang}] the line being said is the latest bubble — one focus`);
  assert.equal(crawl(w).id, w.lines()[w.lines().length - 1].id, `[${c.lang}] …it IS the last row`);
  L.pushAgentChat(c.A, { spoken: true, trace: TA });
  assert.deepEqual(said(w), [c.note, c.ask, c.B, c.A], `[${c.lang}] its record joins its own row`);
  assert.equal(w.rejected.length, 0, `[${c.lang}] ${JSON.stringify(w.rejected)}`);

  // its own start paints it at once (V2-752 kept), and a late record of an OLDER line goes to that row, in place
  w = await wall();
  w.legacy.pushAgentChat(c.B, { voiced: true, trace: TB });
  w.legacy.noteVoiceStarted(TB);
  w.legacy.noteSpokenAloud(c.B.slice(0, 12), false);
  w.legacy.pushAgentChat(c.A, { voiced: true, trace: TA });
  w.legacy.noteVoiceStarted(TA);
  assert.deepEqual(said(w), [c.B.slice(0, 12) + "…", c.A]);
  w.legacy.pushAgentChat(c.B, { spoken: true, trace: TB });
  assert.deepEqual(rows(w), [c.B, c.A], `[${c.lang}] the trace groups a record with its row, it never reorders`);
  // M5: B was settled cut when A's voice started; a record that says more cannot lengthen it — refused, counted
  assert.deepEqual(said(w), [c.B.slice(0, 12) + "…", c.A], `[${c.lang}] M5: a settled line of ours never grows`);
  assert.deepEqual(w.rejected.map((r) => r.reason), ["final_grows"], `[${c.lang}] …and the refusal is counted`);

  // an untraced build keeps painting on the start it has (nothing names a turn on either side)
  w = await wall();
  w.legacy.pushAgentChat(c.A, { voiced: true });
  w.legacy.noteVoiceStarted("");
  assert.deepEqual(said(w), [c.A]);
}

console.log("ok — a reply lands in the latest bubble");
