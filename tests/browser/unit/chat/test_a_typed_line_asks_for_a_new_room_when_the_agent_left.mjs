// test_a_typed_line_asks_for_a_new_room_when_the_agent_left.mjs — the page's answer to «no session».
// Run: node tests/browser/unit/chat/test_a_typed_line_asks_for_a_new_room_when_the_agent_left.mjs
import assert from "node:assert/strict";
const A = await import("../../../../frontend/app/services/voice-arrival.js?v=1");
const { createOutbox } = await import("../../../../frontend/app/services/outbox.js?v=1");

// the decision, one row per state of the page
assert.equal(A.onNoSession({ started: false, starting: false }), "start", "no session of its own: it starts one");
assert.equal(A.onNoSession({ started: false, starting: true }), "wait", "one is already coming up");
assert.equal(A.onNoSession({ started: true, starting: true, agent: false }), "wait");
assert.equal(A.onNoSession({ started: true, watching: true, agent: false }), "wait", "the agent is still being waited for");
assert.equal(A.onNoSession({ started: true, agent: true }), "wait", "the agent is there: its typed door is opening");
assert.equal(A.onNoSession({ started: true, agent: false, watching: false }), "reconnect", "a room the agent left");
assert.equal(A.onNoSession(), "start");

// the handler the session service hands the outbox: it reads the page's state WHEN asked and does that one thing
{
  const st = { started: true, starting: false, watching: false, agent: false }, did = [];
  const h = A.noSession(() => st, () => did.push("start"), () => did.push("reconnect"), (l) => did.push(l));
  assert.equal(h(), "reconnect"); st.agent = true; assert.equal(h(), "wait"); st.started = false; assert.equal(h(), "start");
  assert.deepEqual(did, ["🤖 agent left the room", "reconnect", "start"]);
}

// end to end with the outbox: a page that holds a room the agent left asks for a new one, and the line then lands
const mem = new Map();
const storage = { getItem: (k) => (mem.has(k) ? mem.get(k) : null), setItem: (k, v) => mem.set(k, String(v)) };
let timers = [];
const schedule = (fn) => { timers.push(fn); return fn; };
const page = { started: true, starting: false, watching: false, agent: false, rooms: 1 };
const sent = [];
const box = createOutbox({
  storage, schedule,
  send: async (t) => (page.agent ? (sent.push(t), { ok: true }) : { ok: false, reason: "no_session" }),
  onNoSession: () => {
    const act = A.onNoSession(page);
    if (act === "reconnect" || act === "start") { page.rooms += 1; page.agent = true; }   // the new room has its agent
  },
});
box.add("add a cello lesson on Thursday");
await new Promise((r) => setTimeout(r, 5));
assert.equal(sent.length, 0, "the engine had no session for it");
assert.equal(page.rooms, 2, "the page asked for a new room instead of waiting in the empty one");
assert.equal(box.size(), 1, "and the line is still his until the engine has it");
for (const fn of timers.splice(0)) fn();               // the outbox tries again
await new Promise((r) => setTimeout(r, 5));
assert.deepEqual(sent, ["add a cello lesson on Thursday"]);
assert.equal(box.size(), 0);

// disarm: a page that only waits never leaves the empty room — the line stays undelivered for as long as it tries
const stuck = { started: true, starting: false, watching: false, agent: false, rooms: 1 };
const mem2 = new Map(); let timers2 = [];
const box2 = createOutbox({
  storage: { getItem: (k) => (mem2.has(k) ? mem2.get(k) : null), setItem: (k, v) => mem2.set(k, String(v)) },
  schedule: (fn) => { timers2.push(fn); return fn; },
  send: async () => (stuck.agent ? { ok: true } : { ok: false, reason: "no_session" }),
  onNoSession: () => { if (!stuck.started && !stuck.starting) { stuck.rooms += 1; stuck.agent = true; } },   // the old rule
});
box2.add("x");
for (let i = 0; i < 5; i++) { await new Promise((r) => setTimeout(r, 2)); for (const fn of timers2.splice(0)) fn(); }
await new Promise((r) => setTimeout(r, 2));
assert.equal(stuck.rooms, 1); assert.equal(box2.size(), 1, "the old rule leaves the line waiting in a room nobody is in");
// ── audit 2026-11-17: an agent that is THERE with its typed door closed is waited for no longer than an agent is ──
assert.equal(A.onNoSession({ started: true, agent: true, waitedMs: A.AGENT_WAIT_MS - 1 }), "wait");
assert.equal(A.onNoSession({ started: true, agent: true, waitedMs: A.AGENT_WAIT_MS }), "reconnect", "its door never opened");
assert.equal(A.onNoSession({ started: true, starting: true, agent: true, waitedMs: 1e9 }), "wait", "a room coming up is not counted");
{
  let t = 1000; const st = { started: true, starting: false, watching: false, agent: true }, did = [];
  const h = A.noSession(() => st, () => did.push("start"), () => did.push("reconnect"), (l, x) => did.push(x.state), () => t);
  assert.equal(h(), "wait"); t += 3000; assert.equal(h(), "wait");
  st.starting = true; t += A.AGENT_WAIT_MS; assert.equal(h(), "wait", "a new room coming up starts the count again");
  st.starting = false; assert.equal(h(), "wait"); t += A.AGENT_WAIT_MS - 1; assert.equal(h(), "wait");
  t += 1; assert.equal(h(), "reconnect"); assert.deepEqual(did, ["typed_door_closed", "reconnect"]);
  assert.equal(h(), "wait", "after asking for a new room the count starts over");
}
// disarm on the real file: without the bound, the same page waits for as long as it is asked
{
  const fs = await import("node:fs"), os = await import("node:os"), path = await import("node:path"), url = await import("node:url");
  const real = url.fileURLToPath(new URL("../../../../frontend/app/services/voice-arrival.js", import.meta.url));
  const src = fs.readFileSync(real, "utf8"), bound = 'if (agent) return waitedMs >= AGENT_WAIT_MS ? "reconnect" : "wait";';
  assert.ok(src.includes(bound), "the bound is not where this disarm expects it");
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "arrival-")), copy = path.join(dir, "voice-arrival.mjs");
  fs.writeFileSync(copy, src.replace(bound, 'if (agent) return "wait";'));
  const M = await import(url.pathToFileURL(copy).href);
  let t = 0; const h = M.noSession(() => ({ started: true, agent: true }), () => {}, () => {}, () => {}, () => t);
  for (let i = 0; i < 400; i++) { t += 3000; assert.equal(h(), "wait", "the mutation did not land"); }
  fs.rmSync(dir, { recursive: true, force: true });
}
console.log("ok");
