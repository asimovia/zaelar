// THE STACK SCALE (EnergyGauge.scale) — the contract the gauge draws (2026-10-24).
//
// Tested in Node rather than in a browser because `scale` is deliberately PURE: it is the only piece of the gauge
// with rules, so it can fail on its own, without the DOM.
//
// The rule: the SAME number of bars for every account (more and thinner on a wider screen), each worth the gauge's
// full scale divided by the bars. A cycle owns `capacity / per` of them and lights `balance / per` — «the cycle's
// Energy minus what was spent» — so a small plan lights part of the gauge and the biggest one all of it.
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
assert.equal(barsFor(1400), 30);
assert.equal(barsFor(1000), 20);
assert.equal(barsFor(400), 12);
for (const cap of [500, 1300, 3000, 13000]) {
  assert.equal(scale(cap, cap, { scale: FULL }, WIDE).bars, 30, `every plan draws 30 bars on a wide screen (${cap})`);
}

// ── a small plan owns part of the gauge, the biggest all of it ─────────────────────────────────────────────────
let s = scale(1300, 1300, { scale: FULL, tier: 1 }, WIDE);
assert.equal(s.own, 3, "a 1300 cycle owns 3 of 30");
assert.equal(s.lit, 3, "…and a full cycle lights all of its own");
s = scale(13000, 13000, { scale: FULL, tier: 4 }, WIDE);
assert.equal(s.own, 30);
assert.equal(s.lit, 30);
assert.equal(s.tier, 4);

// ── lit = what is left, proportionally ─────────────────────────────────────────────────────────────────────────
s = scale(1500, 3000, { scale: FULL, tier: 2 }, WIDE);
assert.equal(s.own, 7, "3000 of 13000 is 7 of 30");
assert.equal(s.lit, 3, "1500 left is 3 bars");

// ── any Energy left lights a bar; none lights nothing ──────────────────────────────────────────────────────────
s = scale(397, 500, { scale: FULL, tier: 0 }, WIDE);
assert.equal(s.own, 1);
assert.equal(s.lit, 1, "397 left is NOT an empty gauge");
assert.equal(scale(0, 500, { scale: FULL }, WIDE).lit, 0);

// ── an older control plane sends no scale: the cycle fills the gauge ───────────────────────────────────────────
s = scale(397, 500, null, WIDE);
assert.equal(s.own, 30);
assert.equal(s.lit, 24, "397 of 500 is 24 of 30");

// ── nothing to draw without a capacity; the tier is clamped to the colours there are ───────────────────────────
assert.equal(scale(10, 0, null, WIDE), null);
assert.equal(scale(10, 10, { tier: 9 }, WIDE).tier, 4);

console.log("energy scale: ok");
