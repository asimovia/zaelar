// The old path writes the chat wall as one writer among others (INI-042 #49, the wall plan's commit 3/5; the review's
// F3-2, F3-3 and minors). Drives the REAL `services/wall-legacy.js` and `services/wall-storage.js` on the REAL model.
//
//   · F3-2 — a typed line's engine announcement carries the screen's own id for it (`cid`): on the screen that typed
//     it, it is that line's acknowledgement by the keyboard that wrote it — ONE line, no refusal, nothing compared by
//     text; on another screen, the same line; with no id, a line of this screen is not painted again, another's is;
//   · his line in course is ONE line: live from his first partial, final in place when the gate releases it, gone when
//     the gate rules the room — and a line of his from another door (a probe's text) never takes it over;
//   · a notice is one line per notice id: a retry of the same notice paints nothing new;
//   · a line is painted whole: no length cuts what he typed (10 000 characters stay 10 000);
//   · the reset clears the wall and the old path's state;
//   · the old wall's history (`hb_chat_log`) is moved ONCE into the wall's storage, at the old cap, and its key removed.
//
// Run: node tests/browser/unit/chat_wall/test_the_old_path_is_one_writer_among_others.mjs
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const { wall, cleanDevice } = await import(pathToFileURL(path.join(here, "../chat/wallkit.mjs")).href);
const storage = await import(pathToFileURL(path.join(here, "../../../../frontend/app/services/wall-storage.js")).href);

const ME = "desktop:ab12cd";
let n = 0;
const ok = (name, fn) => Promise.resolve(fn()).then(() => { n += 1; console.log("ok -", name); });

await ok("a typed line and its acknowledgement are one line", async () => {
  const w = await wall();
  w.writer(`keyboard:${ME}`).apply({ op: "append", id: "c_1", role: "you", state: "final", text: "w1" });
  w.legacy.ackTyped("w1", "c_1", ME, ME, cleanDevice);
  assert.deepEqual(w.said().map((l) => l.text), ["w1"]);
  assert.equal(w.counts().rejected, 0, JSON.stringify(w.rejected));
});

await ok("another screen's typed line is that screen's keyboard's line here too", async () => {
  const w = await wall();
  w.legacy.ackTyped("w1", "c_9", "phone:ff00", ME, cleanDevice);
  w.legacy.ackTyped("w1", "c_9", "phone:ff00", ME, cleanDevice);         // announced twice: still one line
  assert.deepEqual(w.lines().map((l) => [l.owner, l.id, l.text]), [["keyboard:phone:ff00", "c_9", "w1"]]);
});

await ok("with no id, this screen's line is not painted again and another's is", async () => {
  const w = await wall();
  w.legacy.ackTyped("w1", "", ME, ME, cleanDevice);
  w.legacy.ackTyped("w2", "", "phone:ff00", ME, cleanDevice);
  assert.deepEqual(w.said().map((l) => l.text), ["w2"]);
});

await ok("his line in course is one line: live, then final in place", async () => {
  const w = await wall();
  w.legacy.setLiveChat("w1");
  w.legacy.setLiveChat("w1 w2");
  const [live] = w.lines();
  assert.equal(live.state, "live");
  w.legacy.youSaid("w1 w2 w3", 5);
  w.legacy.clearLiveChat();                                               // the hold settles after it delivers
  assert.deepEqual(w.lines().map((l) => [l.id, l.state, l.text]), [[live.id, "final", "w1 w2 w3"]]);
});

await ok("a line of his from another door never takes over his line in course", async () => {
  const w = await wall();
  w.legacy.setLiveChat("w1");                                             // he is speaking
  w.legacy.pushChat({ role: "you", text: "w2" });                         // a probe's text, another door
  w.legacy.youSaid("w1 w3", 5);
  assert.deepEqual(w.lines().map((l) => [l.text, l.state]), [["w1 w3", "final"], ["w2", "final"]]);
});

await ok("the room's words leave nothing", async () => {
  const w = await wall();
  w.legacy.setLiveChat("w1 w2");
  w.legacy.clearLiveChat();
  assert.deepEqual(w.lines(), []);
});

await ok("a notice is one line per notice id", async () => {
  const w = await wall();
  w.legacy.notice("w1", "k1");
  w.legacy.pushChat({ role: "you", text: "w2" });
  w.legacy.notice("w1", "k1");                                            // a retry of the same notice
  assert.deepEqual(w.said().map((l) => l.text), ["🔔 w1", "w2"]);
});

await ok("a line is painted whole, however long", async () => {
  const w = await wall();
  w.legacy.ackTyped("x".repeat(10_000), "c_2", "phone:ff00", ME, cleanDevice);
  assert.equal(w.lines()[0].text.length, 10_000);
});

await ok("the reset clears the wall and what the old path owed", async () => {
  const w = await wall();
  w.legacy.pushAgentChat("w1", { voiced: true, trace: "T1" });
  w.legacy.pushChat({ role: "sys", text: "w2" });
  w.legacy.reset();
  w.legacy.noteVoiceStarted("T1", 1);                                     // the owed line went with the reset
  assert.deepEqual(w.lines(), []);
});

await ok("the old wall's history moves over once, at the old cap", async () => {
  const kept = new Map();
  const ls = { getItem: (k) => (kept.has(k) ? kept.get(k) : null), setItem: (k, v) => kept.set(k, v),
               removeItem: (k) => kept.delete(k) };
  const rows = Array.from({ length: 130 }, (_, i) => ({ role: i % 2 ? "agent" : "you", text: `w${i}` }));
  rows.push({ role: "ref", ref: "r1", text: "w-box" });
  kept.set(storage.OLD_KEY, JSON.stringify({ v: 1, at: 7, msgs: rows }));
  const s = storage.createWallStorage(ls);
  const lines = s.load();
  assert.equal(lines.length, storage.CAP);
  assert.deepEqual(lines.at(-1), { id: "old_99", state: "final", text: "w-box", at: 0, owner: "legacy:ref", role: "box",
                                   kind: "ref", data: { role: "ref", ref: "r1", text: "w-box" } });
  assert.ok(lines.every((l) => l.state === "final"));
  assert.equal(kept.has(storage.OLD_KEY), false, "the old key is moved once, then gone");
  assert.equal(s.at(), 7);
  assert.equal(storage.createWallStorage(ls).load().length, storage.CAP, "the second load reads the new key");
});

console.log(`${n} passed`);
