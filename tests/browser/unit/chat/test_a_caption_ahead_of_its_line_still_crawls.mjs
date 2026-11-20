// The agent's line crawls on the wall even when its captions arrive BEFORE the line is owed (2026-11-18).
//
// The captions reach the page straight from the room; the line they belong to reaches it from the body
// (`brain reply` → `pushAgentChat(..., { voiced: true })`). Measured on a loaded, swapping host: the body stalled
// 1-8.7 s, every caption that landed in that gap matched no owed line and was ignored, and the line appeared WHOLE
// when the reply finally arrived. Now the newest caption still sounding is kept, and the line it begins claims it.
//
// Drives the REAL old-path writer (`services/wall-legacy.js`) on the REAL wall model, through `wallkit.mjs`. A caption
// segment is `legacy.noteSpokenAloud(text, final)` — what `session-lk.js` calls for every audio-synced segment.
//
// Disarms (each seen red): no `claimEarly()` in `pushAgentChat` → (1); `early` kept on a final caption → (3); no age
// check in `claimEarly` → (4).
import assert from "node:assert/strict";
import { wall } from "./wallkit.mjs";

const agents = (w) => w.said().filter((l) => l.role === "agent");
const agentTexts = (w) => w.lines().filter((l) => l.role === "agent").map((l) => l.text);
const crawl = (w) => agents(w).find((l) => l.state === "live") || null;

// ── 1 · captions first, the reply late: the line is painted with what was already heard, and keeps crawling ──
for (const [reply, early, more] of [
  ["Te he apuntado la cita del dentista para el martes a las diez.", "Te he apuntado la cita", "Te he apuntado la cita del dentista"],
  ["I've booked the table for four at eight tonight.", "I've booked the", "I've booked the table for four"],
]) {
  const w = await wall();
  w.legacy.noteSpokenAloud(early, false);                    // the body is stalled: no line is owed yet
  assert.deepEqual(agents(w), [], "a caption alone writes nothing");
  w.legacy.pushAgentChat(reply, { voiced: true, trace: "T-" + early.length });
  assert.deepEqual(crawl(w), { role: "agent", text: early, state: "live" },
    `the early caption was lost: ${JSON.stringify(w.said())}`);
  assert.deepEqual(agentTexts(w), [reply], "the line is on the wall, crawling from what was already heard");
  w.legacy.noteSpokenAloud(more, false);
  assert.equal(crawl(w).text, more, "…and it keeps growing with the captions that follow");
}

// ── 2 · a caption that is the beginning of ANOTHER line is not this line's: it stays owed, unwritten ──
{
  const w = await wall();
  w.legacy.noteSpokenAloud("Hace sol en Sevilla", false);
  w.legacy.pushAgentChat("Mañana a las nueve tienes la reunión.", { voiced: true, trace: "T2" });
  assert.equal(crawl(w), null, "an unrelated caption is no evidence this line started");
  assert.deepEqual(agents(w), []);
}

// ── 3 · a FINISHED utterance ahead of the line (a filler, a notice) does not start a later line ──
{
  const w = await wall();
  w.legacy.noteSpokenAloud("Un momento", true);
  w.legacy.pushAgentChat("Un momento, lo busco ahora mismo.", { voiced: true, trace: "T3" });
  assert.equal(crawl(w), null, "a final caption is a finished utterance, not this line sounding");
  assert.deepEqual(agents(w), []);
}

// ── 4 · a stale caption says nothing about a line owed now ──
{
  let t = Date.now();
  const w = await wall({ now: () => t });
  w.legacy.noteSpokenAloud("Ya está", false);
  t += 60000;
  w.legacy.pushAgentChat("Ya está hecho, te lo he dejado en la agenda.", { voiced: true, trace: "T4" });
  assert.equal(crawl(w), null, "a caption a minute old does not paint today's line");
  assert.deepEqual(agents(w), []);
}

console.log("ok — a caption ahead of its line still crawls");
