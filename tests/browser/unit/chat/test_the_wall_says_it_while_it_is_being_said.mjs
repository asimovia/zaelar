// V2-747 — the wall prints the agent's line WHILE the voice says it, and stops where the voice stops.
//
// The operator, session 981dd54c (2026-09-21). V2-745 had just made the wall keep only what was actually
// said; he watched that work and asked for the other ORDER:
//
//   «Pones todo el bloque de texto y asumimos que ese bloque ya es el definitivo. Pero ya sabes que si te
//    corto, te corto el output, y realmente tú luego rectificas el audio y solo dejas lo que has llegado a
//    decir… ¿Ese mismo principio de los subtítulos se puede aplicar al chat? ¿Y solo ir mostrando las
//    palabras a medida que las vas diciendo? Y SI YO TE CORTO, TE PARAS EN ESE MOMENTO Y YA NO IMPRIMES MÁS.»
//
//   «¿Podría[s] poner ese texto un poco más grisáceo, más pálido? O el fondo del mensaje en otro color,
//    QUE DESTAQUE, QUE EN ESTE MOMENTO ES LO QUE ESTÁS LEYENDO.»
//
// The channel is LiveKit's audio-synced transcription, the same one V2-745 already wired in and the same
// one the orb's teleprompter has used since V2-116 — so this is a second READER of a proven channel, not
// a new one. What is new is that the wall no longer paints a line before it has sounded.
//
// ⚠️ The GRACE WINDOW is the half that keeps this from being a regression: with no caption channel at all
// (synchronizer off, a transport that never forwards it) an unstreamed line would sit invisible until the
// NEXT reply settled it. That window is now `bot_speech` (group 6), and the only timer left is the voice's idle grace
// (`IDLE_GRACE_MS`), which group 7 runs to the end.
//
// This drives the REAL old-path wall writer (`services/wall-legacy.js`) on the REAL wall model, through
// `wallkit.mjs`. «The line the voice owes» (`voicedLine()` in the old store) is now the wall's own line of ours in
// state `live`: it shows what was heard (`heard`), or all of it while nothing has been heard yet. A caption segment
// is `legacy.noteSpokenAloud(text, final)` — what `session-lk.js` calls for every audio-synced segment.
import assert from "node:assert/strict";
import { wall, shown } from "./wallkit.mjs";

let w = null;
const agentLines = () => w.said().filter((m) => m.role === "agent").map((m) => m.text);
const reset = async () => { w = await wall(); };
const caption = (text, final) => w.legacy.noteSpokenAloud(text, final);
// the line being said: { full, said } — or null when no line of ours is live
const voiced = () => {
  const l = w.lines().find((x) => x.role === "agent" && x.state === "live");
  return l ? { full: l.text, said: shown(l), heard: l.heard } : null;
};

const REPLY = "Me alegra que lo veas mejor, y te tomo nota de las dos cosas.";

// ══ 1 · NOTHING IS ON SCREEN BEFORE IT HAS SOUNDED ══════════════════════════════════════════════════
// V2-752 — «before it has sounded» now starts EARLIER than it did here. The line is OWED from the moment
// the model produces it and published only when the engine reports the utterance actually started
// (`bot_speech speaking`), so nothing is on screen and nothing is streamable until then. Measured cost of
// the old shape, session fce3eff3: 9 of 24 replies were painted and never sounded.
await reset();
w.legacy.pushAgentChat(REPLY, { voiced: true, trace: "T1" });
assert.equal(voiced(), null, "owed, not yet published: the voice has not begun it");
assert.deepEqual(agentLines(), [], "…and nothing is on the wall either");
w.legacy.noteVoiceStarted("T1");
let v = voiced();
assert.ok(v, "a voiced line must publish what the voice owes, or the wall has nothing to stream");
assert.equal(v.full, REPLY);
assert.equal(v.heard, undefined, "not one word has sounded yet — «el texto que no has dicho no quiero que exista»");
assert.equal(v.said, REPLY, "…so it is shown whole: the caption channel may simply not exist on this build");

// ══ 2 · IT GROWS AS THE VOICE SAYS IT ═══════════════════════════════════════════════════════════════
caption("Me alegra", false);
assert.equal(voiced().said, "Me alegra");
caption("Me alegra que lo veas mejor,", false);
assert.equal(voiced().said, "Me alegra que lo veas mejor,",
  "the caption is cumulative and the wall follows it word by word");
assert.deepEqual(agentLines(), ["Me alegra que lo veas mejor,"], "…and nothing after it is shown");

// ══ 3 · «SI YO TE CORTO, TE PARAS EN ESE MOMENTO» ═══════════════════════════════════════════════════
// The utterance is cancelled mid-sentence: the caption goes final where the audio stopped.
caption("Me alegra que lo veas mejor,", true);
assert.equal(voiced(), null, "settled: the line is no longer being said");
assert.deepEqual(agentLines(), ["Me alegra que lo veas mejor,…"],
  "the history keeps what was HEARD, with the ellipsis that says where it stopped");

// ══ 4 · A LINE THAT SOUNDED WHOLE KEEPS EVERY WORD ══════════════════════════════════════════════════
await reset();
w.legacy.pushAgentChat(REPLY, { voiced: true, trace: "T4" });
caption(REPLY, true);
assert.equal(voiced(), null);
assert.deepEqual(agentLines(), [REPLY], "no ellipsis, no trim: it said all of it");

// ══ 5 · A LINE THAT NEVER SOUNDED AT ALL ════════════════════════════════════════════════════════════
// The +157.1 s case: 14.05 s of audio synthesised, `bot_speech` never left idle. The voice then went on
// to say something ELSE, which is the evidence V2-745 requires before removing anything.
// V2-752 — it is now never WRITTEN either, which is the step the operator asked for after watching this
// one work: «vas poniendo de golpe un párrafo… y luego lo borras».
await reset();
w.legacy.pushAgentChat(REPLY, { voiced: true, trace: "T5" });
caption("Sí…", true);                                 // the next turn's filler — a different line
assert.equal(voiced(), null, "a caption that is not this line's speech never streams it");
assert.ok(!agentLines().includes(REPLY), "a line the voice never began is not on the wall at all");
w.legacy.pushAgentChat("Un segundo.", { voiced: true, trace: "T5b" });    // the next reply settles the owed one
assert.ok(!agentLines().includes(REPLY), "…and settling does not resurrect it");

// ══ 6 · NO CAPTION CHANNEL AT ALL → THE WALL BEHAVES AS IT DID ══════════════════════════════════════
// Silence on a channel is never read as evidence about the voice — the same doctrine as V2-745's removal
// guard. V2-752 replaced the 1200 ms grace window that used to serve this case with `bot_speech speaking`,
// the engine's own statement that the utterance reached the speaker: it does not expire, it does not
// depend on the caption transport, and it is not a guess. The line reaches the wall WHOLE, exactly as it
// did before V2-747 — that has not changed and must not.
await reset();
w.legacy.pushAgentChat(REPLY, { voiced: true, trace: "T6" });
assert.deepEqual(agentLines(), [], "…but not before the voice has begun it");
w.legacy.noteVoiceStarted("T6");
assert.ok(voiced(), "it starts hopeful: the channel may be there");
assert.equal(voiced().heard, undefined, "not one caption segment has arrived");
assert.deepEqual(agentLines(), [REPLY], "no segment, and the line is on the wall whole — nothing is lost");

// ══ 7 · A LIVE CHANNEL IS NOT GIVEN UP ON HALFWAY THROUGH A SENTENCE ════════════════════════════════
await reset();
w.legacy.pushAgentChat(REPLY, { voiced: true, trace: "T7" });
caption("Me alegra", false);
w.flush();                                                // every timer the writer set has run its course
const after = voiced();
assert.ok(after && after.said === "Me alegra",
  "a live channel must not be given up on halfway through a sentence");

// ══ 8 · A LINE THAT IS NOT VOICED AT ALL IS NOT STREAMED ════════════════════════════════════════════
// A written reply, a notification, a peer line: there is no voice to follow, so it appears whole at once.
await reset();
w.legacy.pushAgentChat("🔔 Te recuerdo la cita de las 11:30.", {});
assert.equal(voiced(), null);
assert.deepEqual(agentLines(), ["🔔 Te recuerdo la cita de las 11:30."]);

// ══ 9 · THE WALL RENDERS `heard`, AND MARKS THE LINE BEING READ ═════════════════════════════════════
// The renderer's half of the contract. The wall is one node per line, drawn from what the line SHOWS (`shown`: cut
// to `heard`) — the model's own function, so the two cannot disagree about what goes inside the bubble — and its
// classes come from the host's `lineClasses`, read here from its source.
const fs = await import("node:fs/promises");
const chatWall = await fs.readFile(new URL("../../../../frontend/app/components/ChatWall.js", import.meta.url), "utf8");
const view = await fs.readFile(new URL("../../../../frontend/chat-wall/view.js", import.meta.url), "utf8");
assert.ok(/const said = shown\(line/.test(view), "the view draws what the line SHOWS: what was heard of it");
const k = chatWall.indexOf("const speaking =");
assert.ok(k > 0, "the `speaking` predicate was not found in ChatWall.js — was it renamed?");
const pred = chatWall.slice(k, chatWall.indexOf(";", k));
assert.ok(/l\.state === "live"/.test(pred) && /l\.heard/.test(pred),
  "the line being read is the live line of ours, by what was heard of it");
assert.ok(chatWall.includes('(speaking ? " cw-speaking" : "")'),
  "«que destaque, que en este momento es lo que estás leyendo» — the line being read carries its own mark");
// V2-752 — a line with nothing HEARD yet is drawn WHOLE, not skipped (group 6 measures it on the model: `heard`
// undefined shows all of it). It is on the wall because the voice started it (`bot_speech speaking`).
assert.equal(shown({ role: "agent", state: "live", text: REPLY, heard: undefined }), REPLY,
  "a line already sounding but with no caption yet is shown whole, never skipped");
assert.ok(/const plain = l\.state !== "final"/.test(chatWall) && chatWall.includes('plain ? h("div", { class: "cw-msg-body" }, said)'),
  "it renders what was HEARD, as plain text — a half-said sentence routinely holds an unclosed `*`");
const css = await fs.readFile(new URL("../../../../frontend/app/styles.css", import.meta.url), "utf8");
assert.ok(/\.cw-msg\.agent\.cw-speaking\s*\{/.test(css), "the mark needs a style or it marks nothing");

console.log("ok — the wall says it while it is being said");
