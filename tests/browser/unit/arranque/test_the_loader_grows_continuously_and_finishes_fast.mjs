// ============================================================================
// test_the_loader_grows_continuously_and_finishes_fast.mjs — the boot loader's growth schedule (node 4.492).
//
// The operator (2026-11-12): the mesh must compose itself little by little — one neuron at the top, another at the
// bottom, one on the left, two at the top… — at a steady cadence, never in two or three batches tied to the boot
// phases; and when the boot is ready the rest develops very fast and the loader hands over.
// Drives the pure `growStep` / `growthOrder` of frontend/app/components/boot-anim.js frame by frame.
//
// Run: node tests/browser/unit/arranque/test_the_loader_grows_continuously_and_finishes_fast.mjs [path-to-boot-anim]
// ============================================================================
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";
import path from "node:path";

const src = process.argv[2] ? pathToFileURL(path.resolve(process.argv[2])).href
                            : new URL("../../../../frontend/app/components/boot-anim.js", import.meta.url).href;
const { growStep, growthOrder, GROW, STAGE_FLOOR } = await import(src);

const N = 240, DT = 1 / 60;
/** Run the schedule: stage changes at the given seconds, ready at `readyAt`. Returns the node count per frame. */
function run({ until, stages = { 0: 2 }, readyAt = Infinity }) {
  let p = 0, floor = 0, t = 0;
  const counts = [];
  while (t < until) {
    for (const [at, st] of Object.entries(stages)) if (t >= Number(at) && STAGE_FLOOR[st] > floor) floor = STAGE_FLOOR[st];
    p = growStep(p, DT, t, floor, t >= readyAt);
    counts.push({ t, n: Math.round(p * N), p });
    t += DT;
  }
  return counts;
}

// ── 1. continuous, driven by time: it grows between phases, in many small steps, never a batch ──────────────────
{
  const c = run({ until: 15, stages: { 0: 2, 6: 3 } });
  for (let i = 1; i < c.length; i++) {
    assert.ok(c[i].p >= c[i - 1].p, `the growth went backwards at ${c[i].t.toFixed(2)} s`);
    assert.ok(c[i].n - c[i - 1].n <= 2, `a batch of ${c[i].n - c[i - 1].n} neurons in one frame at ${c[i].t.toFixed(2)} s`);
  }
  const at = (s) => c.find((x) => x.t >= s).n;
  assert.ok(at(0.5) >= 1 && at(0.5) <= 20, `the first half second shows a few neurons, not a block: ${at(0.5)}`);
  assert.ok(at(2) > at(1) && at(3) > at(2) && at(4) > at(3) && at(5) > at(4),
    `with no new phase the mesh still grows every second: ${[1, 2, 3, 4, 5].map(at)}`);
  assert.ok(at(5) >= 0.3 * N, `the first seconds compose a good part of the mesh: ${at(5)}`);
  const distinct = new Set(c.map((x) => x.n)).size;
  assert.ok(distinct >= 150, `the mesh grows one neuron at a time (distinct counts ${distinct})`);
  assert.ok(Math.max(...c.map((x) => x.n)) < N, "only ready completes the mesh");
  // no long freeze while still under the ceiling: every 0.5 s window adds at least one neuron during the first 10 s
  for (let s = 0.5; s < 10; s += 0.5) assert.ok(at(s + 0.5) > at(s), `the growth froze between ${s} and ${s + 0.5} s`);
}

// ── 2. ready: whatever was reached, the rest develops within GROW.FINISH_S ───────────────────────────────────────
for (const readyAt of [0.4, 3, 12, 40]) {
  const c = run({ until: readyAt + 1, readyAt });
  const done = c.find((x) => x.p >= 1);
  assert.ok(done, `ready at ${readyAt} s never completed the mesh`);
  assert.ok(done.t - readyAt <= GROW.FINISH_S + DT * 2, `ready at ${readyAt} s took ${(done.t - readyAt).toFixed(3)} s`);
  const before = c.filter((x) => x.t < readyAt).at(-1);
  if (before) assert.ok(before.p < 1, "complete before ready");
}

// ── 3. the order: every neuron once, the fronts take turns (top, bottom, left…) in short runs ─────────────────
{
  let seed = 7;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const pts = Array.from({ length: N }, () => {
    const a = rnd() * Math.PI * 2, r = 0.14 + 0.86 * Math.sqrt(rnd());
    return { x: 640 + Math.cos(a) * r * 400, y: 368 + Math.sin(a) * r * 280 };
  });
  const order = growthOrder(pts, 640, 368, rnd);
  assert.equal(order.length, N);
  assert.equal(new Set(order).size, N, "every neuron appears exactly once");
  const region = (i) => Math.round(Math.atan2(pts[i].y - 368, pts[i].x - 640) / (Math.PI / 3));
  const first = order.slice(0, 24).map(region);
  assert.ok(new Set(first).size >= 4, `the first neurons come from several sides: ${first}`);
  let run1 = 1, longest = 1;
  for (let k = 1; k < 120; k++) { run1 = region(order[k]) === region(order[k - 1]) ? run1 + 1 : 1; longest = Math.max(longest, run1); }
  assert.ok(longest <= 6, `one side grew ${longest} neurons in a row: the fronts must take turns`);
  const d = (i) => Math.hypot(pts[i].x - 640, pts[i].y - 368);
  const inner = order.slice(0, 30).reduce((s, i) => s + d(i), 0) / 30, outer = order.slice(-30).reduce((s, i) => s + d(i), 0) / 30;
  assert.ok(inner < outer * 0.7, `the mesh grows outwards from the ring (${inner.toFixed(0)} vs ${outer.toFixed(0)})`);
}

console.log("ok");
