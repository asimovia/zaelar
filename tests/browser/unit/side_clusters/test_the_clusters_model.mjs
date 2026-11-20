// test_the_clusters_model.mjs — what a «Clusters» row and the connect gate say (`rowView`, `gateView` of
// frontend/side/clusters/clusters.js), with no DOM.
// Run: node tests/browser/unit/side_clusters/test_the_clusters_model.mjs
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const { rowView, gateView } = await import(path.join(root, "frontend/side/clusters/clusters.js"));
const t = (k, v) => (v ? `${k}(${Object.values(v).join("|")})` : k);

// connected, public, a handle, two peers: every part of the line, the plural word, the count summed by the backend
assert.deepEqual(rowView({ name: "commons", connected: true, public: true, handle: "h1", online: ["p1", "p2"],
                           cluster_id: "c_abc", msgs: 5 }, t),
  { name: "commons", connected: true, isPublic: true, id: "c_abc",
    meta: "chat.connectedchat.clusterAs(h1)chat.clusterPeers(2|p1, p2)chat.clusterMsgs(5)" });
// one peer takes the singular word
assert.equal(rowView({ name: "x", connected: true, online: ["p1"], msgs: 1 }, t).meta,
             "chat.connectedchat.clusterPeer(1|p1)chat.clusterMsgs(1)");
// a credentialled cluster that is offline: nobody there, no count yet, no id, not public
assert.deepEqual(rowView({ name: "saved" }, t),
  { name: "saved", connected: false, isPublic: false, id: "",
    meta: "chat.disconnectedchat.clusterNobodychat.clusterMsgs(0)" });
// an `online` that is not a list counts as nobody, never as its characters
assert.match(rowView({ name: "y", online: "p1" }, t).meta, /chat\.clusterNobody/);

// the gate: absent with nothing pending; the backend's question when it sent one, the default otherwise
assert.equal(gateView(null, t), null);
assert.deepEqual(gateView({}, t), { question: "chat.clusterConfirmQ" });
assert.deepEqual(gateView({ question: "Connect to commons?" }, t), { question: "Connect to commons?" });
console.log("ok");
