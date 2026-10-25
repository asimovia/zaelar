// THE STACK SCALE (EnergyGauge.scale) — the contract the gauge draws (2026-10-24).
//
// Tested in Node rather than in a browser because `scale` is deliberately PURE: it is the only piece of the gauge
// with rules, so it can fail on its own, without the DOM.
//
// The rule: the SAME number of bars for every account (more and thinner on a wider screen); the whole row is the current
// cycle and the lit bars are what is left of it, in proportion — «the cycle's Energy minus what was spent». The plan
// shows in the colour.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const src = readFileSync(path.join(here, "../../../../frontend/app/components/EnergyGauge.js"), "utf8");

// The pure functions are extracted: importing the module would pull in dom.js/store.js/i18n.js, which need a browser.
const i = src.indexOf("export function barsFor");
const j = src.indexOf("// When an account url");
assert.ok(i > 0 && j > i, "the scale is not where it was in EnergyGauge.js — renamed?");
const { scale, barsFor } = await import("data:text/javascript," + encodeURIComponent(src.slice(i, j)));

const FULL = 13000;            // the gauge's full scale as the cloud sends it (the biggest cycle)
const WIDE = 1400;

// ── the same bars for everyone, by screen ──────────────────────────────────────────────────────────────────────
assert.equal(barsFor(1400), 50);
assert.equal(barsFor(1000), 25);
assert.equal(barsFor(400), 20);
for (const cap of [500, 1300, 3000, 13000]) {
  assert.equal(scale(cap, cap, { scale: FULL }, WIDE).bars, 50, `every plan draws 50 bars on a wide screen (${cap})`);
}

// ── the whole row is THIS cycle; lit = what is left of it, in proportion ──────────────────────────────────────
let s = scale(394.6, 398, { scale: FULL, tier: 0 }, WIDE);
assert.equal(s.own, 50, "the current plan fills the gauge");
assert.equal(s.lit, 50, "394 of 398 is (nearly) full — the operator's own account, which lit 1 bar of 30 before");
s = scale(1500, 3000, { scale: FULL, tier: 2 }, WIDE);
assert.equal(s.lit, 25, "half the cycle left is half the bars");
assert.equal(s.tier, 2, "the plan shows in the colour");
s = scale(650, 1300, { scale: FULL, tier: 1 }, 820);
assert.equal(s.bars, 20);
assert.equal(s.lit, 10);

// ── any Energy left lights a bar; none lights nothing ──────────────────────────────────────────────────────────
assert.equal(scale(1, 13000, { tier: 4 }, WIDE).lit, 1, "almost empty is not empty");
assert.equal(scale(0, 500, { scale: FULL }, WIDE).lit, 0);

// ── nothing to draw without a capacity; the tier is clamped to the colours there are ───────────────────────────
assert.equal(scale(10, 0, null, WIDE), null);
assert.equal(scale(10, 10, { tier: 9 }, WIDE).tier, 4);

console.log("energy scale: ok");
