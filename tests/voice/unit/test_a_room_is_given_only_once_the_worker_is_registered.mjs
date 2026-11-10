// test_a_room_is_given_only_once_the_worker_is_registered.mjs — V2-873: the page waits for the AGENT.
// Run: node tests/voice/unit/test_a_room_is_given_only_once_the_worker_is_registered.mjs
import assert from "node:assert/strict";
const A = await import("../../../frontend/app/services/voice-arrival.js?v=1");

// the token answers
assert.equal(A.tokenVerdict({ ok: true, token: "jwt" }), "token");
assert.equal(A.tokenVerdict({ ok: false, error: "voice_starting" }), "starting");
assert.equal(A.tokenVerdict({ ok: false, error: "engine_stopped" }), "stopped");

// who is in the room
const room = (ids) => ({ remoteParticipants: new Map(ids.map((id) => [id, { identity: id, isAgent: id.startsWith("agent-") }])) });
assert.equal(A.agentPresent(room([])), false);
assert.equal(A.agentPresent(room(["operator-1"])), false);
assert.equal(A.agentPresent(room(["agent-AJ_x"])), true);
assert.equal(A.agentPresent(null), false);

// fake clock
let now = 0, timers = [];
const setT = (fn, ms) => { const t = { at: now + ms, fn }; timers.push(t); return t; };
const clearT = (t) => { timers = timers.filter((x) => x !== t); };
const tick = (ms) => { now += ms; for (const t of timers.filter((x) => x.at <= now)) { clearT(t); t.fn(); } };

// A room the agent never joins: after the bound a new room (a new token) is asked, AGENT_TRIES times, then stop.
// The overlay's «ready» is never set on the way.
let tokens = 0, ready = false, unavailable = false;
const retry = A.boundedRetry(A.AGENT_TRIES, 1000, setT, clearT);
function start() {
  tokens += 1;
  const r = room(["operator-1"]);                       // the agent never comes
  A.watchAgent(r, () => { if (!retry.arm(start)) unavailable = true; }, A.AGENT_WAIT_MS, setT, clearT);
  if (A.agentPresent(r)) ready = true;
}
start();
for (let i = 0; i < 10; i++) tick(A.AGENT_WAIT_MS + 1000);
assert.equal(tokens, 1 + A.AGENT_TRIES, `a new room is asked for each time, bounded: ${tokens}`);
assert.equal(unavailable, true, "past the bound the page says the agent is not available");
assert.equal(ready, false, "never «ready» without the agent");

// An agent that joins cancels the watch.
let missing = 0;
const r2 = room(["operator-1"]);
const cancel = A.watchAgent(r2, () => { missing += 1; }, A.AGENT_WAIT_MS, setT, clearT);
r2.remoteParticipants.set("agent-AJ_y", { identity: "agent-AJ_y", isAgent: true });
cancel();
tick(A.AGENT_WAIT_MS * 2);
assert.equal(missing, 0);

// A worker registering: bounded waits on 503 voice_starting.
const sr = A.boundedRetry(3, 3000, setT, clearT);
let asked = 0;
const ask = () => { asked += 1; if (!sr.arm(ask)) asked += 100; };
ask(); for (let i = 0; i < 6; i++) tick(3000);
assert.equal(asked, 4 + 100, "three waits, then it stops asking");
console.log("ok");
