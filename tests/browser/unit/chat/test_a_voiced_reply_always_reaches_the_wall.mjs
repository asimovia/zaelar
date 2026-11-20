// ============================================================================
// test_a_voiced_reply_always_reaches_the_wall.mjs — V2-850, node 4.357.
//
// Measured on a cloud session (2026-11-04): he typed «send Raquel a message, ask her how it's going» twice.
// Both times the engine produced a reply, the voice said it and the spoken record came back — and the chat
// wall stayed EMPTY. He read it as the agent ignoring him. Two shapes, each enough on its own:
//
//   1. The wait filler («a ver…») opens the utterance and the reply streams INTO it, so the turn's only
//      `bot_speech speaking` arrives BEFORE the reply is owed. The owed line then waited for a start that
//      had already happened.
//   2. After the reply event the turn said one more sentence (the verdict's line: «Eso sí: no le he enviado
//      nada…»). The spoken record was therefore LONGER than the owed line, the wall read «not a prefix» as
//      «a cancelled line» and muted it.
//
// The rule kept (V2-752): a line the voice never began is never written. The rule added: a line whose
// voice is already sounding is written at once, and a spoken record that EXTENDS the owed line is written
// whole — a spoken record is proof it sounded.
//
// Drives the REAL old-path writer (`services/wall-legacy.js`) on the REAL wall model, through `wallkit.mjs`.
//
// Run: node tests/browser/unit/chat/test_a_voiced_reply_always_reaches_the_wall.mjs
// ============================================================================
import assert from "node:assert/strict";
import { wall } from "./wallkit.mjs";

const said = (w) => w.said().filter((l) => l.role === "agent").map((l) => l.text);

const T = "T6·2a8b";
const REPLY = "…ya lo tienes redactado en la app de mensajería. Míralo y dime si lo envío.";
const TAIL = " Eso sí: no le he enviado nada a nadie, no ha salido ningún mensaje.";

// ── 1 · the filler opened the utterance: the reply is written when it is owed ─────────────────────────────
let w = await wall();
w.legacy.noteVoiceStarted(T);                            // «a ver…» — before the reply exists
w.legacy.pushAgentChat(REPLY, { voiced: true, trace: T });
assert.deepEqual(said(w), [REPLY], "the voice was already saying this turn: its line is written now");
assert.equal(w.lines()[0].state, "live", "…and it is the line being said");
w.legacy.pushAgentChat(REPLY + TAIL, { spoken: true, trace: T });
// The line is still LIVE here (no idle, no settle): M5 (only a FINAL line of ours never grows) does not apply, and the
// record is proof the tail sounded. The same record with no start seen (group 2) writes the tail; this one must too.
const tailKept = JSON.stringify(said(w)) === JSON.stringify([REPLY + TAIL]);
const tailSeen = JSON.stringify(w.said());
assert.equal(w.lines().filter((l) => l.role === "agent").length, 1, "the record joins the line, never a second bubble");

// another turn's sounding voice never paints this line, and an idle voice paints nothing
w = await wall();
w.legacy.noteVoiceStarted("T5·53b6");
w.legacy.pushAgentChat(REPLY, { voiced: true, trace: T });
assert.deepEqual(said(w), [], "somebody else's utterance does not write this line");
w = await wall();
w.legacy.noteVoiceStarted(T); w.legacy.noteVoiceIdle();
w.legacy.pushAgentChat(REPLY, { voiced: true, trace: T });
assert.deepEqual(said(w), [], "a voice that already went idle is not this line's start");

// ── 2 · no start seen at all: the spoken record that EXTENDS the line writes it ───────────────────────────
w = await wall();
w.legacy.pushAgentChat(REPLY, { voiced: true, trace: T });
w.legacy.pushAgentChat(REPLY + TAIL, { spoken: true, trace: T });
assert.deepEqual(said(w), [REPLY + TAIL],
  "a spoken record longer than the owed line is that line plus the verdict's sentence — written, never muted");

// the same in English, untraced build
w = await wall();
w.legacy.pushAgentChat("Drafted it on the messages card.", { voiced: true });
w.legacy.pushAgentChat("Drafted it on the messages card. Nothing has been sent yet.", { spoken: true });
assert.deepEqual(said(w), ["Drafted it on the messages card. Nothing has been sent yet."]);

// ── 3 · the kept rule: a cancelled line is still never written ─────────────────────────────────────────────
w = await wall();
w.legacy.pushAgentChat(REPLY, { voiced: true, trace: T });
w.legacy.dropUnspokenLine(T);
w.legacy.pushAgentChat(REPLY + TAIL, { spoken: true, trace: T });
assert.deepEqual(said(w), [], "a turn cut before it sounded stays off the wall (V2-752)");

// group 1's tail, checked last so every other group above still reports
assert.ok(tailKept,
  "…and the spoken record, with its tail, replaces it in place — the voice said the tail; the wall must show it. " +
  `Got ${tailSeen}`);

console.log("ok — a voiced reply always reaches the wall");
