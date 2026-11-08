// test_a_typed_line_is_kept_until_the_engine_has_it.mjs — the outbox (frontend/app/services/outbox.js).
// Live 2026-11-08: a request typed during an engine stall went down a data channel nobody was listening on, the
// in-memory queue died with the reload, and the next session greeted him. A line is kept until `/api/chat` says ok.
import assert from "node:assert/strict";
import { createOutbox, OUTBOX_KEY, OUTBOX_TTL_MS } from "../../../../frontend/app/services/outbox.js";

function store() { const m = new Map(); return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)) }; }
const flush = () => new Promise((r) => setTimeout(r, 0));

// 1 · delivered → gone
{
  const s = store(), sent = [];
  const ob = createOutbox({ storage: s, send: async (t) => { sent.push(t); return { ok: true }; }, schedule: () => 1 });
  ob.add("put some music here");
  await flush();
  assert.deepEqual(sent, ["put some music here"]); assert.equal(ob.size(), 0);
}
// 2 · the engine cannot take it (network) → kept, a retry is scheduled, and a RELOAD (a new outbox on the same
//     storage) delivers it
{
  const s = store(); let timers = 0;
  const down = createOutbox({ storage: s, send: async () => ({ ok: false, reason: "network" }), schedule: () => ++timers });
  down.add("vicios ocultos, her music");
  await flush();
  assert.equal(down.size(), 1, "the line survives the failure"); assert.ok(timers >= 1, "and is tried again");
  const sent = [];
  const reloaded = createOutbox({ storage: s, send: async (t) => { sent.push(t); return { ok: true }; }, schedule: () => 1 });
  await reloaded.drain();
  assert.deepEqual(sent, ["vicios ocultos, her music"]); assert.equal(reloaded.size(), 0);
}
// 3 · no session yet → the session is brought up and the line waits for it
{
  const s = store(); let up = 0;
  const ob = createOutbox({ storage: s, send: async () => ({ ok: false, reason: "no_session" }), onNoSession: () => up++, schedule: () => 1 });
  ob.add("hello");
  await flush();
  assert.equal(up, 1); assert.equal(ob.size(), 1);
}
// 4 · an old line is not an order any more
{
  const s = store(); let t = 1_000_000;
  const ob = createOutbox({ storage: s, send: async () => ({ ok: false, reason: "network" }), now: () => t, schedule: () => 1 });
  ob.add("stale");
  await flush();
  t += OUTBOX_TTL_MS + 1;
  assert.equal(ob.size(), 0);
  assert.ok(JSON.parse(s.getItem(OUTBOX_KEY)).length <= 1);
}
// 5 · order is kept: the second line waits for the first
{
  const s = store(), sent = []; let fail = true;
  const ob = createOutbox({ storage: s, send: async (t) => { if (fail) return { ok: false, reason: "network" }; sent.push(t); return { ok: true }; }, schedule: () => 1 });
  ob.add("one"); await flush(); ob.add("two"); await flush();
  fail = false; await ob.drain();
  assert.deepEqual(sent, ["one", "two"]);
}
console.log("ok");
