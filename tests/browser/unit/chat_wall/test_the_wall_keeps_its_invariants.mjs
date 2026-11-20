// ============================================================================
// test_the_wall_keeps_its_invariants.mjs — the chat wall's model under thousands of random actions (INI-042 #49).
//
// Four writers (his ear, his keyboard, our mouth, the tasks) send random actions — appends with new and taken ids,
// updates, replaces and deletes of their own lines and of the others', a forged owner now and then. After EVERY
// action the invariants of the plan hold:
//   M1 one id, one line · M2 only appended at the end, the order of two lines never changes · M3 a writer only
//   changes its own lines · M4 a final line of his never changes · M5 a final line of ours only shortens to what
//   sounded · M6 two equal lines are two lines · M9 a line comes after every line it answers that existed.
// A forged owner is refused. Seeded, so a red is reproducible.
//
// Run: node tests/browser/unit/chat_wall/test_the_wall_keeps_its_invariants.mjs
// ============================================================================
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, "../../../..");
const { createModel } = await import(path.join(root, "frontend/chat-wall/model.js"));

let seed = 20261120;
const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);
const pick = (xs) => xs[Math.floor(rnd() * xs.length)];

const OWNERS = ["ear:holder", "keyboard", "mouth", "tasks"];
const ROLE_OF = { "ear:holder": "you", keyboard: "you", mouth: "agent", tasks: "box" };
const rejected = [];
const m = createModel({ cap: 10000, onRejected: (r) => rejected.push(r) });
const w = Object.fromEntries(OWNERS.map((o) => [o, m.writer(o)]));
let made = 0;

const snap = () => new Map(m.lines().map((l) => [l.id, l]));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

for (let i = 0; i < 6000; i++) {
  const me = pick(OWNERS);
  const before = snap();
  const ids = [...before.keys()];
  const kind = rnd();
  let op;
  if (kind < 0.35 || ids.length === 0) {
    const id = rnd() < 0.15 && ids.length ? pick(ids) : `l${++made}`;
    const re = ROLE_OF[me] === "agent" && ids.length ? [pick(ids)] : undefined;
    op = { op: "append", id, role: ROLE_OF[me], state: pick(["pending", "live", "final"]), text: pick(["w1", "w1", "w2 w3", "w4"]), re };
  } else if (kind < 0.75) {
    op = { op: "update", id: pick(ids), text: rnd() < 0.5 ? pick(["w5", "w6 w7"]) : undefined,
           heard: rnd() < 0.4 ? Math.floor(rnd() * 6) : undefined, state: rnd() < 0.4 ? pick(["live", "final", "pending"]) : undefined };
  } else if (kind < 0.85) {
    op = { op: "replace", id: pick(ids), data: { v: i } };
  } else {
    op = { op: "delete", id: pick(ids) };
  }
  const forged = rnd() < 0.05 ? pick(OWNERS.filter((o) => o !== me)) : undefined;
  if (forged) op.owner = forged;
  const n0 = rejected.length;
  const res = w[me].apply(op);
  if (forged) assert.ok(!res.ok && rejected.length === n0 + 1 && rejected.at(-1).reason === "forged_owner", `forged ${i}`);
  const after = snap();
  const lines = m.lines();

  assert.equal(new Set(lines.map((l) => l.id)).size, lines.length, `M1 at ${i}`);
  for (let k = 1; k < lines.length; k++) assert.ok(lines[k - 1].n < lines[k].n, `M2 order at ${i}`);
  const kept = [...before.keys()].filter((id) => after.has(id));
  const keptAfter = lines.map((l) => l.id).filter((id) => before.has(id));
  assert.deepEqual(keptAfter, kept, `M2 nothing moves at ${i}`);
  if (op.op === "append" && res.ok && !res.ack) assert.equal(lines.at(-1).id, op.id, `M2 appended at the end at ${i}`);
  for (const [id, b] of before) {
    const a = after.get(id);
    if (!a) { assert.ok(b.owner === me && b.state !== "final" && op.op === "delete" && op.id === id, `M3/M4 deleted at ${i}`); continue; }
    if (!same(a, b)) assert.ok(b.owner === me && !forged && op.id === id, `M3 a foreign change at ${i}`);
    if (b.state === "final" && b.role === "you") assert.ok(same(a, b), `M4 at ${i}`);
    if (b.state === "final" && b.role === "agent") {
      assert.equal(a.text, b.text, `M5 text at ${i}`);
      const was = b.heard === undefined ? b.text.length : b.heard, now = a.heard === undefined ? a.text.length : a.heard;
      assert.ok(now <= was, `M5 grows at ${i}`);
    }
  }
  for (const l of lines) for (const r of l.re) {
    const c = after.get(r);
    if (c) assert.ok(c.n < l.n, `M9 at ${i}`);
  }
}
{ // M6: two equal lines are two lines, never merged by text
  const m2 = createModel(), mouth = m2.writer("mouth");
  mouth.apply({ op: "append", id: "a", role: "agent", text: "w1" });
  mouth.apply({ op: "append", id: "b", role: "agent", text: "w1" });
  assert.deepEqual(m2.lines().map((l) => l.id), ["a", "b"]);
}
assert.ok(rejected.length > 500, `the run tried the refusals (${rejected.length})`);
console.log(`ok · ${made} lines made · ${rejected.length} refused`);
