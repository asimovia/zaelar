// ============================================================================
// test_the_wall_is_in_the_order_things_were_committed.mjs — node 4.572.
//
// Operator's rule (2026-11-17): every bubble is stamped at the moment it is COMMITTED — his words when they are
// final, the agent's line when the voice starts it — and the wall shows them in exactly that order. That day his
// line landed BELOW the agent's reply to it. Measured: on the eager end-of-turn path the attention gate's directed
// verdict reached the client 24–90 ms BEFORE his final transcript; the hold dropped a verdict that found nothing
// held, so his line waited for the NEXT turn's verdict and was pushed after the reply it had caused.
//
// Two mechanisms, each disarmed once: (1) a verdict rules a final that lands just after it (`attention_hold.js`,
// LATCH_MS); (2) a row is inserted by its commit stamp, so a line released late still lands where it was said
// (`store.pushChat` → `_insertByAt`). Both drive the REAL modules.
//
// Run: node tests/browser/unit/chat/test_the_wall_is_in_the_order_things_were_committed.mjs
// ============================================================================
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, "../../../..");
const { createAttentionHold, LATCH_MS } = await import(path.join(root, "frontend/app/services/attention_hold.js"));

const store = readFileSync(path.join(root, "frontend/app/core/store.js"), "utf8");
const i = store.indexOf("const _CHAT_MARKERS");
const j = store.indexOf("// Convenience helpers used across services");
const p = store.indexOf("export const pushChat");
assert.ok(i > 0 && j > i && p > 0, "the chat-wall slice or pushChat was not found in store.js — renamed?");
const shim = `
let msgs = [];
let _capSeq = 0;
const setChatMsgs = (fn) => { msgs = fn(msgs); };
const _capChat = (xs) => xs;
const createSignal = (v) => { let _v = v; return [() => _v, (n) => { _v = n; }]; };
${store.slice(p, store.indexOf("\n", p))}
${store.slice(i, j)}
export const reset = () => { msgs = []; _pendingVoiced = null; _owedQueue = []; noteVoiceIdle(); };
export const wall = () => msgs.map(m => (m.role === "agent" ? "Z: " : "H: ") + m.text);
export const rows = () => msgs;
`;
const S = await import("data:text/javascript," + encodeURIComponent(shim));

// The hold wired to the store the way sse.js wires it: the joined paragraph is his bubble, stamped `at`.
function wired(mode = "smart") {
  const settled = [];
  const hold = createAttentionHold({
    mode: () => mode, holdMs: 10_000, setTimer: () => 1, clearTimer: () => {},
    deliver: (text, isFinal, judged, whole, at) => { if (whole) S.pushChat({ role: "you", text, at }); },
    settled: (how) => settled.push(how),
  });
  return { hold, settled };
}
const reply = (text, trace, at) => { S.pushAgentChat(text, { voiced: true, trace }); S.noteVoiceStarted(trace, at); S.noteVoiceIdle(); };

// ── 1 · the measured race: verdict 50 ms BEFORE the transcript; reply; next turn ───────────────────────────
for (const [lang, a, r1, b, r2] of [
  ["es", "Ponme la agenda de mañana", "Ahí la tienes.", "¿Y a qué hora es la primera?", "A las nueve."],
  ["en", "Show me tomorrow's agenda", "Here it is.", "And when is the first one?", "At nine."],
]) {
  S.reset();
  const { hold } = wired();
  hold.verdict("", true, { reason: "active_window", at: 10_000 });     // the gate rules first…
  hold.spoken(a, true, 10_050);                                         // …his final lands 50 ms later
  assert.deepEqual(S.wall(), ["H: " + a], `[${lang}] his line is on the wall the moment it is final, before any reply`);
  assert.equal(hold.pending(), 0, `[${lang}] nothing is left waiting for a verdict that already came`);
  reply(r1, "T1", 12_000);
  hold.verdict("", true, { reason: "active_window", at: 20_000 });
  hold.spoken(b, true, 20_040);
  reply(r2, "T2", 21_500);
  assert.deepEqual(S.wall(), ["H: " + a, "Z: " + r1, "H: " + b, "Z: " + r2],
    `[${lang}] the wall is the commit order: his line, its reply, his next line, its reply`);
  const ats = S.rows().map(m => m.at);
  assert.deepEqual(ats, [10_050, 12_000, 20_040, 21_500], `[${lang}] each row carries the stamp of the event that committed it`);
}

// ── 2 · a line released LATE lands where it was said, not where it was released ────────────────────────────
{
  S.reset();
  const { hold } = wired();
  hold.spoken("Pon música tranquila", true, 30_000);                    // no verdict for it yet…
  reply("Pongo algo tranquilo.", "T3", 31_200);                         // …the reply sounds…
  hold.verdict("", true, { reason: "active_window", at: 36_000 });      // …and the next verdict releases it
  assert.deepEqual(S.wall(), ["H: Pon música tranquila", "Z: Pongo algo tranquilo."],
    "his line is stamped when it was final (30.0 s) and sorts above the reply that sounded at 31.2 s");
  S.pushChat({ role: "you", text: "gracias", at: 31_200 });
  assert.equal(S.wall()[2], "H: gracias", "equal stamps keep arrival order (stable insert)");
}

// ── 3 · the latch is bounded and spent, and only a ruling latches ──────────────────────────────────────────
{
  const { hold } = wired();
  hold.verdict("", true, { reason: "active_window", at: 40_000 });
  hold.spoken("uno", true, 40_030);
  hold.spoken("dos", true, 40_060);
  assert.equal(hold.pending(), 1, "one verdict, one turn: the latch is spent on the first final it releases");
}
{
  const { hold } = wired();
  hold.verdict("", true, { reason: "active_window", at: 50_000 });
  hold.spoken("mucho después", true, 50_000 + LATCH_MS + 1);
  assert.equal(hold.pending(), 1, "past LATCH_MS a verdict rules nothing new — the line waits for its own");
}
for (const reason of ["wakeword_interim", "wakeword_spot", "addressed_reply", "hard_interrupt"]) {
  const { hold } = wired();
  hold.verdict("", true, { reason, at: 60_000 });
  hold.spoken("Johnny, abre el reloj", true, 60_040);
  assert.equal(hold.pending(), 1, `a «${reason}» signal is not a ruling on a turn: it latches nothing`);
}
{
  const { hold } = wired();
  hold.spoken("Johnny, ponme la radio", true, 70_000);
  hold.verdict("", true, { reason: "wakeword", at: 70_100 });           // the usual order: release what is held
  hold.spoken("pues el otro día en la tele", true, 70_400);             // a room line right after
  assert.equal(hold.pending(), 1, "a verdict that released a held line arms no latch for the next one");
}

// ── 4 · ambient first: the room's line never reaches the wall, in either order (V2-647 kept) ───────────────
{
  S.reset();
  const { hold, settled } = wired();
  hold.verdict("pero este, si es el contable, está vigilado", false, { reason: "no_wakeword", at: 80_000 });
  hold.spoken("pero este, si es el contable, está vigilado", true, 80_060);
  assert.deepEqual(S.wall(), [], "ruled ambient before it landed: never painted");
  assert.equal(hold.pending(), 0, "…and not left waiting for a fail-open to paint it later");
  assert.deepEqual(settled, ["dropped"], "the live caption is cleared with it");
  hold.spoken("Johnny, ¿qué hora es?", true, 80_300);
  assert.equal(hold.pending(), 1, "a line the ambient verdict's text does not cover still waits for its own ruling");
}

// ── 5 · always mode stamps too ──────────────────────────────────────────────────────────────────────────────
{
  S.reset();
  const { hold } = wired("always");
  hold.spoken("hola", true, 90_000);
  assert.equal(S.rows()[0].at, 90_000, "no gate, same stamp: the moment it was final");
}

console.log("ok — the wall is in commit order");
