// ============================================================================
// test_the_wall_is_in_the_order_things_were_committed.mjs — node 4.572.
//
// Operator's complaint (2026-11-17): his line landed BELOW the agent's reply to it. Measured: on the eager
// end-of-turn path the attention gate's directed verdict reached the client 24–90 ms BEFORE his final transcript;
// the hold dropped a verdict that found nothing held, so his line waited for the NEXT turn's verdict and was pushed
// after the reply it had caused.
//
// The order rule changed on purpose (the wall plan §5.1, decided by the operator): a line's place is where it
// STARTS. Lines are appended, never inserted by time — his spoken line takes its place at his first partial, our line
// at its voice's start. What stays pinned is the complaint: his line is above the reply it caused.
//
// Two mechanisms, each disarmed once: (1) a verdict rules a final that lands just after it (`attention_hold.js`,
// LATCH_MS); (2) his line in course is ONE line from his first partial, made final IN PLACE when the gate releases
// it (`wall-legacy.js`, `youSaid`), so a line released late still stands where he started saying it. Both drive the
// REAL modules: the hold wired to the REAL old-path writer on the REAL wall model (`wallkit.mjs`), the way `sse.js`
// wires it (`deliver` whole → `legacy.youSaid`, `settled` → `legacy.clearLiveChat`, the caption → `setLiveChat`).
//
// Run: node tests/browser/unit/chat/test_the_wall_is_in_the_order_things_were_committed.mjs
// ============================================================================
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { wall as freshWall } from "./wallkit.mjs";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const { createAttentionHold, LATCH_MS } = await import(
  pathToFileURL(path.join(root, "frontend/app/services/attention_hold.js")).href);

let W = null;
const reset = async () => { W = await freshWall(); };
const wall = () => W.said().map((l) => (l.role === "agent" ? "Z: " : "H: ") + l.text);
const rows = () => W.lines();

// The hold wired to the old path's writer the way sse.js wires it: the joined paragraph is his line, stamped `at`.
function wired(mode = "smart") {
  const settled = [];
  const hold = createAttentionHold({
    mode: () => mode, holdMs: 10_000, setTimer: () => 1, clearTimer: () => {},
    deliver: (text, isFinal, judged, whole, at) => { if (whole) W.legacy.youSaid(text, at); },
    settled: (how) => { settled.push(how); W.legacy.clearLiveChat(); },
  });
  // `sse.captionPartial`: what the hold already keeps for this turn, then the partial being typed.
  const partial = (text) => {
    const said = hold.spokenSoFar(), now = String(text || "").trim();
    W.legacy.setLiveChat(said && now ? said + " " + now : (said || now));
  };
  return { hold, settled, partial };
}
const reply = (text, trace, at) => {
  W.legacy.pushAgentChat(text, { voiced: true, trace });
  W.legacy.noteVoiceStarted(trace, at);
  W.legacy.noteVoiceIdle();
  W.flush();                                                            // the idle grace runs out: the line settles
};

// ── 1 · the measured race: verdict 50 ms BEFORE the transcript; reply; next turn ───────────────────────────
for (const [lang, a, r1, b, r2] of [
  ["es", "Ponme la agenda de mañana", "Ahí la tienes.", "¿Y a qué hora es la primera?", "A las nueve."],
  ["en", "Show me tomorrow's agenda", "Here it is.", "And when is the first one?", "At nine."],
]) {
  await reset();
  const { hold } = wired();
  hold.verdict("", true, { reason: "active_window", at: 10_000 });     // the gate rules first…
  hold.spoken(a, true, 10_050);                                         // …his final lands 50 ms later
  assert.deepEqual(wall(), ["H: " + a], `[${lang}] his line is on the wall the moment it is final, before any reply`);
  assert.equal(hold.pending(), 0, `[${lang}] nothing is left waiting for a verdict that already came`);
  reply(r1, "T1", 12_000);
  hold.verdict("", true, { reason: "active_window", at: 20_000 });
  hold.spoken(b, true, 20_040);
  reply(r2, "T2", 21_500);
  assert.deepEqual(wall(), ["H: " + a, "Z: " + r1, "H: " + b, "Z: " + r2],
    `[${lang}] the wall is in order: his line, its reply, his next line, its reply`);
  assert.deepEqual(rows().map((m) => m.at), [10_050, 12_000, 20_040, 21_500],
    `[${lang}] each line carries the stamp of the event that committed it`);
  assert.deepEqual(rows().map((m) => m.state), ["final", "final", "final", "final"], `[${lang}] all settled`);
  assert.deepEqual(rows()[1].re, [rows()[0].id], `[${lang}] our reply names the line of his it answers`);
  assert.equal(W.counts().rejected, 0, `[${lang}] the wall refused nothing: ${JSON.stringify(W.rejected)}`);
}

// ── 2 · a line released LATE stands where he STARTED saying it (§5.1), above the reply it caused ───────────
for (const [lang, parts, final, r] of [
  ["es", ["Pon", "Pon música"], "Pon música tranquila", "Pongo algo tranquilo."],
  ["en", ["Play", "Play some"], "Play some quiet music", "Playing something quiet."],
]) {
  await reset();
  const { hold, partial } = wired();
  for (const p of parts) partial(p);                                    // his first partial takes his line's place
  const his = rows()[0];
  assert.deepEqual(W.said(), [{ role: "you", text: parts[1], state: "live" }], `[${lang}] his line in course, live`);
  hold.spoken(final, true, 30_000);                                     // no verdict for it yet…
  partial("");                                                          // (sse firms the caption up with the final)
  reply(r, "T3", 31_200);                                               // …the reply sounds…
  hold.verdict("", true, { reason: "active_window", at: 36_000 });      // …and the next verdict releases it
  assert.deepEqual(wall(), ["H: " + final, "Z: " + r],
    `[${lang}] his line is above the reply it caused, though the gate released it after the reply sounded`);
  assert.equal(rows()[0].id, his.id, `[${lang}] ONE line from his first partial to the release — no second bubble`);
  assert.deepEqual(rows().map((m) => m.state), ["final", "final"], `[${lang}] made final in place`);
  assert.equal(rows()[0].at, 30_000, `[${lang}] his line carries the stamp of the moment it was final`);
  assert.deepEqual(rows()[1].re, [his.id], `[${lang}] the reply names his line as its cause`);
  // §5.1: nothing is inserted by time — a line that never had a partial is appended where it is committed, even
  // with an older stamp (the old wall sorted it by `at`; `_insertByAt` is gone on purpose).
  W.legacy.pushChat({ role: "you", text: "gracias", at: 31_000 });
  assert.equal(wall()[2], "H: gracias", `[${lang}] appended at the end, never inserted by its stamp`);
}

// ── 3 · the latch is bounded and spent, and only a ruling latches ──────────────────────────────────────────
{
  await reset();
  const { hold } = wired();
  hold.verdict("", true, { reason: "active_window", at: 40_000 });
  hold.spoken("uno", true, 40_030);
  hold.spoken("dos", true, 40_060);
  assert.equal(hold.pending(), 1, "one verdict, one turn: the latch is spent on the first final it releases");
}
{
  await reset();
  const { hold } = wired();
  hold.verdict("", true, { reason: "active_window", at: 50_000 });
  hold.spoken("mucho después", true, 50_000 + LATCH_MS + 1);
  assert.equal(hold.pending(), 1, "past LATCH_MS a verdict rules nothing new — the line waits for its own");
}
for (const reason of ["wakeword_interim", "wakeword_spot", "addressed_reply", "hard_interrupt"]) {
  await reset();
  const { hold } = wired();
  hold.verdict("", true, { reason, at: 60_000 });
  hold.spoken("Johnny, abre el reloj", true, 60_040);
  assert.equal(hold.pending(), 1, `a «${reason}» signal is not a ruling on a turn: it latches nothing`);
}
{
  await reset();
  const { hold } = wired();
  hold.spoken("Johnny, ponme la radio", true, 70_000);
  hold.verdict("", true, { reason: "wakeword", at: 70_100 });           // the usual order: release what is held
  hold.spoken("pues el otro día en la tele", true, 70_400);             // a room line right after
  assert.equal(hold.pending(), 1, "a verdict that released a held line arms no latch for the next one");
}

// ── 4 · ambient first: the room's line never stays on the wall, in either order (V2-647 kept) ──────────────
{
  await reset();
  const { hold, settled } = wired();
  hold.verdict("pero este, si es el contable, está vigilado", false, { reason: "no_wakeword", at: 80_000 });
  hold.spoken("pero este, si es el contable, está vigilado", true, 80_060);
  assert.deepEqual(wall(), [], "ruled ambient before it landed: never painted");
  assert.equal(hold.pending(), 0, "…and not left waiting for a fail-open to paint it later");
  assert.deepEqual(settled, ["dropped"], "the live caption is cleared with it");
  hold.spoken("Johnny, ¿qué hora es?", true, 80_300);
  assert.equal(hold.pending(), 1, "a line the ambient verdict's text does not cover still waits for its own ruling");
}
{
  // …and with his line already in course from its partials: the gate ruling the room DELETES it.
  await reset();
  const { hold, partial } = wired();
  partial("pero este");
  partial("pero este, si es el contable");
  assert.equal(rows().length, 1, "one line in course");
  hold.verdict("pero este, si es el contable, está vigilado", false, { reason: "no_wakeword", at: 81_000 });
  hold.spoken("pero este, si es el contable, está vigilado", true, 81_050);
  assert.deepEqual(rows(), [], "the room's line in course is deleted when the gate rules it ambient (latched)");
  partial("y luego se fue");
  hold.spoken("y luego se fue sin pagar", true, 82_000);
  partial("");
  hold.verdict("y luego se fue sin pagar", false, { reason: "no_wakeword", at: 82_100 });
  assert.deepEqual(rows(), [], "…and when the verdict comes after the final (held, then dropped)");
  assert.equal(W.counts().rejected, 0, `nothing refused: ${JSON.stringify(W.rejected)}`);
}

// ── 5 · always mode stamps too ──────────────────────────────────────────────────────────────────────────────
{
  await reset();
  const { hold } = wired("always");
  hold.spoken("hola", true, 90_000);
  assert.equal(rows()[0].at, 90_000, "no gate, same stamp: the moment it was final");
  assert.equal(rows()[0].state, "final");
}

console.log("ok — the wall is in the order things started");
