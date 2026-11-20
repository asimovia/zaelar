// THE CHAT WALL MUST NOT ARRIVE LATE (V2-116, session b403c979 from 2026-08-18).
//
// Operator report: “the agent is talking to me, it does not appear in the subtitles, the text does not appear in the chat
// for its response … the response has taken more than a minute from when I heard it by voice until you put it
// on the chat wall”.
//
// Measured in that session’s durable log: the response is GENERATED and rendered on the wall when the
// LiveKit `transcript` arrives, which is not emitted until the conversation item closes—in other words, until TTS
// has finished speaking the ENTIRE response:
//     reply 12:32:13.844 → transcript 12:32:19.267   (5,4 s)
//     reply 12:33:11.376 → transcript 12:33:23.611   (12,2 s)
// The fix pushes the text to the wall as soon as the model generates it, and merges the subsequent `transcript` by
// PREFIX. This tests the pure component where it can fail on its own: `pushAgentChat` deduplication — now in the old
// path's writer (`services/wall-legacy.js`), driven on the REAL wall model through `wallkit.mjs`.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { wall } from "./wallkit.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, "../../../..");

// ── 1) the seam: sse.js pushes the response to the wall on the `reply` event, without waiting for the transcript ──────────
const sse = readFileSync(path.join(root, "frontend/app/services/sse.js"), "utf8");
// The FlashBrain reply branch of the old path (a `conv` event — the manager's session — is left by an earlier
// branch that also names `reply`: the manager writes its own lines, INI-042 #49).
const at = sse.indexOf('} else if (d.kind === "brain" && /reply/.test(String(d.label || ""))) {');
assert.ok(at > 0, "the FlashBrain `reply` branch was not found in sse.js — was it renamed?");
const replyBranch = sse.slice(at, sse.indexOf("} else if", at + 10));
assert.ok(replyBranch.includes("legacy.pushAgentChat("),
  "the FlashBrain `reply` branch must push the text to the wall NOW; otherwise, the wall depends again on " +
  "TTS finishing speaking (5-12 s measured)");
assert.ok(/d\.role === "assistant"/.test(replyBranch),
  "…and only the assistant's (a `reply` without the assistant role is not text the agent said)");
// and the SUBTITLES remain synchronized with the audio, not this
assert.ok(!replyBranch.includes("captionSeg"),
  "the subtitles are NOT fed from here: they are synchronized with the audio (session-lk.js)");

// ── 2) pushAgentChat prefix deduplication, on the old path's REAL writer and the wall's REAL model ──────────────
// What is tested is the merge RULE of a line that is not owed to the voice (no `voiced`): the ladder against the LAST
// line. One change is deliberate — M5 (the wall plan, commit 3/5): a FINAL line of ours never grows, so a fuller text
// after a fragment is a line of its own, counted (`extended`), never a rewrite of the fragment already shown (c).
const agents = (w) => w.said().filter((l) => l.role === "agent");

// (a) the REAL case: it is rendered on generation, and the identical transcript arriving 12 s later does NOT duplicate
let w = await wall();
const reply = "Según los resultados, el lanzamiento más destacado de Ferrari en 2026 es el Ferrari F80.";
w.legacy.pushAgentChat(reply);
w.legacy.pushAgentChat(reply);
assert.equal(agents(w).length, 1, "the later transcript must not duplicate the bubble");

// (b) barge-in: the transcript arrives TRUNCATED → the complete text is preserved, not two bubbles
w = await wall();
w.legacy.pushAgentChat(reply);
w.legacy.pushAgentChat("Según los resultados, el lanzamiento");
assert.equal(agents(w).length, 1, "a cut utterance must not leave two bubbles");
assert.equal(agents(w)[0].text, reply, "the WHOLE text wins (what the agent meant to say)");

// (c) the reverse: a fragment arrives first and then the full text. M5: the fragment is final and never grows; the
// full text is its own line, and the wall counts the extension instead of rewriting a line already shown.
w = await wall();
w.legacy.pushAgentChat("Según los resultados");
w.legacy.pushAgentChat(reply);
assert.deepEqual(agents(w).map((l) => l.text), ["Según los resultados", reply],
  "M5: the fragment stays as shown, the full text is written whole after it");
assert.equal(w.legacy.counts().extended, 1, "…and the extension is counted, never silent");
assert.equal(w.rejected.length, 0, `no refused action: ${JSON.stringify(w.rejected)}`);

// (d) the waiting filler (💬, V2-114) does NOT merge with the response: they are two genuinely spoken things
w = await wall();
w.legacy.pushAgentChat("💬 Espera…");
w.legacy.pushAgentChat(reply);
assert.equal(agents(w).length, 2, "the filler and the reply are separate bubbles");

// (e) two different responses remain two
w = await wall();
w.legacy.pushAgentChat("Son las tres.");
w.legacy.pushAgentChat("Ya te he puesto la música.");
assert.equal(agents(w).length, 2);

// (f) the 🔔 notify marker continues to be normalized (previous behavior, not broken)
w = await wall();
w.legacy.pushAgentChat("He creado el widget «X».");
w.legacy.pushAgentChat("🔔 He creado el widget «X».");
assert.equal(agents(w).length, 1, "🔔 still merges with the same text without its marker");

console.log("chat wall promptness: OK");
