// ============================================================================
// test_two_lines_of_one_turn_are_two_bubbles.mjs — demo 2026-10-22 (Marisa).
//
// «It was called Marisa.» continued the turn that had just answered «Done.», so the reply «Yeah — there's no
// Marisa in your chat list…» carried the SAME trace (`T54`). The wall identified the line the voice is saying by
// trace, so both bubbles crawled the second line — the operator saw the same message twice, both stuck mid-word —
// and the settle trimmed the first row the trace found: the old one.
//
// It drives the REAL old-path writer (`services/wall-legacy.js`) on the REAL wall model (the kit in `../chat/`) and
// replays that order of events. The line being said is now the wall's own line of ours in state `live`.
// Run: node tests/browser/unit/widgets/test_two_lines_of_one_turn_are_two_bubbles.mjs
// ============================================================================
import assert from "node:assert/strict";
import { wall } from "../chat/wallkit.mjs";

const MARISA = "Yeah — there's no Marisa in your chat list, though. Tell me the number she shows under and I'll open it.";
const w = await wall();
const L = w.legacy;
const agents = () => w.said().filter((m) => m.role === "agent");
const rows = () => w.lines().filter((m) => m.role === "agent");
// the wall's own rule for «this bubble is the line being said»: our line, live
const crawling = () => rows().filter((m) => m.state === "live");

// line 1 of T54 — said and settled
L.pushAgentChat("Done.", { voiced: true, trace: "T54" });
L.noteVoiceStarted("T54");
L.noteSpokenAloud("Done.", true);

// line 2 of the SAME turn starts sounding
L.pushAgentChat(MARISA, { voiced: true, trace: "T54" });
L.noteVoiceStarted("T54");
L.noteSpokenAloud("Yeah — there's no Marisa in your chat list, though.", false);

assert.equal(crawling().length, 1, `the crawl is drawn in ${crawling().length} bubbles: ${JSON.stringify(crawling())}`);
assert.equal(crawling()[0].text, MARISA);
assert.deepEqual(agents().map((m) => m.text), ["Done.", "Yeah — there's no Marisa in your chat list, though."]);

// it is cut mid-sentence: the trim lands on ITS row, and «Done.» stays «Done.»
L.settleAgentSpoken();
const texts = agents().map((m) => m.text);
assert.equal(texts.filter((t) => t === "Done.").length, 1, `«Done.» was overwritten: ${JSON.stringify(texts)}`);
assert.deepEqual(texts, ["Done.", "Yeah — there's no Marisa in your chat list, though.…"], JSON.stringify(texts));

// the late spoken record of the turn lands on the newest line, never as a third bubble
L.pushAgentChat("Yeah — there's no Marisa in your chat list, though.", { spoken: true, trace: "T54" });
assert.equal(agents().length, 2, JSON.stringify(agents()));
assert.deepEqual(agents().map((m) => m.text), texts, "…and it changes neither row");
assert.equal(w.rejected.length, 0, JSON.stringify(w.rejected));

console.log("ok — two lines of one turn are two bubbles");
process.exit(0);
