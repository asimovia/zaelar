// ============================================================================
// test_two_lines_of_one_turn_are_two_bubbles.mjs — demo 2026-10-22 (Marisa).
//
// «It was called Marisa.» continued the turn that had just answered «Done.», so the reply «Yeah — there's no
// Marisa in your chat list…» carried the SAME trace (`T54`). The wall identifies the line the voice is saying by
// trace, so both bubbles crawled the second line — the operator saw the same message twice, both stuck mid-word —
// and the settle trimmed the first row the trace found: the old one.
//
// It MOUNTS the real store and replays that order of events.
// Run: node tests/browser/unit/widgets/test_two_lines_of_one_turn_are_two_bubbles.mjs
// ============================================================================
import assert from "node:assert/strict";

const mem = new Map([["hb_lang", "en"], ["hb_i18n_en", JSON.stringify({})]]);
globalThis.localStorage = { getItem: k => (mem.has(k) ? mem.get(k) : null), setItem: (k, v) => mem.set(k, String(v)),
                            removeItem: k => mem.delete(k) };
globalThis.fetch = async () => ({ ok: true, json: async () => ({}), text: async () => "" });
globalThis.document = { documentElement: { lang: "en", setAttribute(){}, style: { setProperty(){} } },
                        querySelectorAll: () => [], querySelector: () => null, addEventListener(){},
                        createElement: () => ({ style:{}, classList:{ add(){}, remove(){} }, appendChild(){}, setAttribute(){} }),
                        head: { appendChild(){} }, body: { appendChild(){} } };
globalThis.window = { addEventListener(){}, location: { href: "http://localhost/" } };

const store = await import("../../../../frontend/app/core/store.js?v=2");
const Marisa = "Yeah — there's no Marisa in your chat list, though. Tell me the number she shows under and I'll open it.";
const agents = () => store.chatMsgs().filter(m => m.role === "agent");
// the ChatWall's own rule for «this bubble is the line being said»
const crawling = () => {
  const say = store.voicedLine();
  return agents().filter(m => say && say.streaming && (say.trace && m.trace ? m.trace === say.trace : m.text === say.full));
};

// line 1 of T54 — said and settled
store.pushAgentChat("Done.", { voiced: true, trace: "T54" });
store.noteVoiceStarted("T54");
store.pushCaptionSeg("s1", "Done.", true);

// line 2 of the SAME turn starts sounding
store.pushAgentChat(Marisa, { voiced: true, trace: "T54" });
store.noteVoiceStarted("T54");
store.pushCaptionSeg("s2", "Yeah — there's no Marisa in your chat list, though.", false);

assert.equal(crawling().length, 1, `the crawl is drawn in ${crawling().length} bubbles: ${JSON.stringify(crawling())}`);
assert.equal(crawling()[0].text, Marisa);

// it is cut mid-sentence: the trim lands on ITS row, and «Done.» stays «Done.»
store.settleAgentSpoken();
const texts = agents().map(m => m.text);
assert.equal(texts.filter(t => t === "Done.").length, 1, `«Done.» was overwritten: ${JSON.stringify(texts)}`);
assert.equal(texts.filter(t => t.startsWith("Yeah — there's no Marisa")).length, 1, JSON.stringify(texts));

// the late spoken record of the turn lands on the newest line, never as a third bubble
store.pushAgentChat("Yeah — there's no Marisa in your chat list, though.", { spoken: true, trace: "T54" });
assert.equal(agents().length, 2, JSON.stringify(agents()));

console.log("ok — two lines of one turn are two bubbles");
process.exit(0);
