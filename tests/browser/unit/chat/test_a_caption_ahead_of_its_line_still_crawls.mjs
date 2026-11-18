// The agent's line crawls on the wall even when its captions arrive BEFORE the line is owed (2026-11-18).
//
// The captions reach the page straight from the room; the line they belong to reaches it from the body
// (`brain reply` → `pushAgentChat(..., { voiced: true })`). Measured on a loaded, swapping host: the body stalled
// 1-8.7 s, every caption that landed in that gap matched no owed line and was ignored, and the line appeared WHOLE
// when the reply finally arrived. Now the newest caption still sounding is kept, and the line it begins claims it.
//
// Disarms (each seen red): no `_claimEarlyCaption()` in `pushAgentChat` → (1); `_earlyCaption` kept on a final
// caption → (3); no age check → (4).
import assert from "node:assert/strict";

const mem = new Map();
globalThis.localStorage = {
  getItem: k => (mem.has(k) ? mem.get(k) : null),
  setItem: (k, v) => mem.set(k, String(v)),
  removeItem: k => mem.delete(k),
};
globalThis.window = { addEventListener() {}, location: { href: "http://127.0.0.1/" } };
globalThis.document = { addEventListener() {}, documentElement: { style: { setProperty() {} } } };

const store = await import("../../../../frontend/app/core/store.js");
const agentLines = () => store.chatMsgs().filter(m => m.role === "agent").map(m => m.text);
const reset = () => { store.setChatMsgs(() => []); store.settleAgentSpoken(); store.pushCaptionSeg("zz", "", true); };

// ── 1 · captions first, the reply late: the line is painted with what was already heard, and keeps crawling ──
for (const [reply, early, more] of [
  ["Te he apuntado la cita del dentista para el martes a las diez.", "Te he apuntado la cita", "Te he apuntado la cita del dentista"],
  ["I've booked the table for four at eight tonight.", "I've booked the", "I've booked the table for four"],
]) {
  reset();
  store.pushCaptionSeg("s1", early, false);                  // the body is stalled: no line is owed yet
  assert.deepEqual(agentLines(), [], "a caption alone writes nothing");
  store.pushAgentChat(reply, { voiced: true, trace: "T-" + early.length });
  const v = store.voicedLine();
  assert.ok(v && v.streaming && v.heard === early, `the early caption was lost: ${JSON.stringify(v)}`);
  assert.deepEqual(agentLines(), [reply], "the line is on the wall, crawling from what was already heard");
  store.pushCaptionSeg("s1", more, false);
  assert.equal(store.voicedLine().heard, more, "…and it keeps growing with the captions that follow");
}

// ── 2 · a caption that is the beginning of ANOTHER line is not this line's: it stays owed, unwritten ──
reset();
store.pushCaptionSeg("s2", "Hace sol en Sevilla", false);
store.pushAgentChat("Mañana a las nueve tienes la reunión.", { voiced: true, trace: "T2" });
assert.equal(store.voicedLine(), null, "an unrelated caption is no evidence this line started");
assert.deepEqual(agentLines(), []);

// ── 3 · a FINISHED utterance ahead of the line (a filler, a notice) does not start a later line ──
reset();
store.pushCaptionSeg("s3", "Un momento", true);
store.pushAgentChat("Un momento, lo busco ahora mismo.", { voiced: true, trace: "T3" });
assert.equal(store.voicedLine(), null, "a final caption is a finished utterance, not this line sounding");
assert.deepEqual(agentLines(), []);

// ── 4 · a stale caption says nothing about a line owed now ──
reset();
const realNow = Date.now;
try {
  store.pushCaptionSeg("s4", "Ya está", false);
  Date.now = () => realNow() + 60000;
  store.pushAgentChat("Ya está hecho, te lo he dejado en la agenda.", { voiced: true, trace: "T4" });
  assert.equal(store.voicedLine(), null, "a caption a minute old does not paint today's line");
} finally {
  Date.now = realNow;
}

console.log("ok — a caption ahead of its line still crawls");
