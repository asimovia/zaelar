// ============================================================================
// test_the_side_column_models.mjs — the models of the side panel's Connectors and Network columns (INI-042 #49).
//
// Connectors: families in the order he expects them, unknown ones after (alphabetically), a row with no family under
// infra; Google is one row whose state counts its services. Network: an answer is «on» only with a relationships array
// (a 404 is null, a stub `{}` is off); the four blocks resolve names, keep only connected agents, cap recent at 15.
//
// Run: node tests/browser/unit/side_columns/test_the_side_column_models.mjs
// ============================================================================
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const conn = await import(path.join(root, "frontend/side/conectores/model.js"));
const red = await import(path.join(root, "frontend/side/red/model.js"));

// ── Connectors ──
const rows = [{ id: "zz", family: "zeta" }, { id: "tg", family: "mensajeria" }, { id: "ab", family: "alfa" },
              { id: "nofam" }, { id: "g", family: "google" }, { id: "yt", family: "video" }, { id: "wa", family: "mensajeria" }];
const fams = conn.byFamily(rows);
assert.deepEqual(fams.map(([f]) => f), ["google", "mensajeria", "video", "infra", "alfa", "zeta"]);
assert.deepEqual(fams[1][1].map((r) => r.id), ["tg", "wa"], "rows keep their order inside a family");
assert.deepEqual(fams[3][1].map((r) => r.id), ["nofam"], "a row with no family is infra");
assert.deepEqual(conn.byFamily(null), []);
assert.deepEqual(conn.liveState({ services: [{ connected: true }, { connected: false }, { connected: true }] }), { on: true, n: 2, total: 3 });
assert.deepEqual(conn.liveState({ services: [{ connected: false }] }), { on: false, n: 0, total: 1 });
assert.deepEqual(conn.liveState({ connected: 1 }), { on: true });
assert.deepEqual(conn.liveState({}), { on: false });

// ── Network ──
assert.equal(red.isOn(null), false, "a 404 is off");
assert.equal(red.isOn({}), false, "a stub is off");
assert.equal(red.isOn({ relationships: [] }), true);
const net = {
  relationships: [{ cid: "marta", name: "Marta", status: "accepted", peer: "abcd", grants: [{ item: "calendar" }, { item: "notes" }] },
                  { cid: "luis", name: "", status: "accepted", peer: "ef01" },
                  { cid: "pepe", name: "Pepe", status: "pending", grants: [{ item: "x" }] }],
  cards: [{ id: "c9", type: "request", name: "Pepe" }],
  recent: [{ cid: "marta", dir: "in", label: "freebusy", item: "calendar" }, { cid: "luis", dir: "out", op: "query" },
           { cid: "nobody", op: "ping" }, ...Array.from({ length: 20 }, (_, i) => ({ cid: "marta", op: "op" + i }))],
};
const b = red.blocks(net);
assert.deepEqual(b.pending, net.cards);
assert.deepEqual(b.relationships, [{ name: "Marta", peer: "abcd" }, { name: "luis", peer: "ef01" }], "only accepted, a missing name shows the id");
assert.deepEqual(b.grants, [{ cid: "marta", name: "Marta", items: ["calendar", "notes"] }], "a pending relationship shares nothing");
assert.equal(b.recent.length, 15);
assert.deepEqual(b.recent.slice(0, 3), [{ text: "← freebusy · calendar", who: "Marta" }, { text: "→ query", who: "luis" },
                                        { text: "ping", who: "nobody" }]);
assert.deepEqual(red.blocks(null), { pending: [], relationships: [], grants: [], recent: [] });
console.log("ok — side column models");
