// The widget catalogue's model (frontend/side/apps/model.js) under Node: which rows are widgets, which scope each
// one lands in, and the order. Run by test_the_catalogue_is_a_component_of_its_own.py.
import assert from "node:assert/strict";
import { SCOPES, scopeOf, tilesOf, widgetsOf } from "../../../../frontend/side/apps/model.js";

const rows = widgetsOf([
  { id: "w-b", name: "Beta", surface: "user", origin: "builtin", forked: false },
  { id: "w-a", name: "Alpha", surface: "user", origin: "builtin", forked: false },
  { id: "w-f", name: "Fork", surface: "user", origin: "user", forked: true },
  { id: "w-m", name: "Mine", surface: "user", origin: "user", forked: false },
  { id: "w-s", name: "Surface", surface: "system", origin: "system" },
  null,
]);
assert.deepEqual(rows.map((w) => w.id), ["w-b", "w-a", "w-f", "w-m"], "only user-surface rows are widgets");
assert.deepEqual(widgetsOf(undefined), []);

const sys = tilesOf(rows, "system");
assert.deepEqual(sys.map((x) => x.w.id), ["w-a", "w-b", "w-f"], "System: the shipped ones and the forked one, by name");
assert.deepEqual(sys.map((x) => x.customized), [false, false, true], "a forked shipped widget is drawn customised");
assert.ok(sys.every((x) => !x.forkOf));

const mine = tilesOf(rows, "custom");
assert.deepEqual(mine.map((x) => x.w.id), ["w-f", "w-m"], "Custom: what he built and what he forked");
assert.deepEqual(mine.map((x) => x.forkOf), [true, false], "under Custom the fork says what it is a copy of");
assert.ok(mine.every((x) => !x.customized), "under Custom the fork is his widget, never pale");

assert.equal(scopeOf("custom").id, "custom");
assert.equal(scopeOf("nonsense").id, "system", "an unknown scope is the first one");
assert.deepEqual(SCOPES.map((s) => s.id), ["system", "custom"]);
console.log("ok");
