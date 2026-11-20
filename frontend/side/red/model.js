// side/red/model.js — the Network column's reading of one GET /api/a2a/network answer (V2-866). No DOM, no imports.
/** A real answer, never a stub `{}`: A2A off (its routes 404) is null, and an off network draws no tab and no body. */
export const isOn = (net) => Array.isArray((net || {}).relationships);
/** The four blocks over one read: pending cards, connected agents, what he shares with each, recent activity. */
export function blocks(net) {
  const n = net || {}, rels = n.relationships || [], connected = rels.filter((r) => r.status === "accepted");
  const name = (cid) => (rels.find((r) => r.cid === cid) || {}).name || cid || "?";
  const arrow = (d) => (d === "in" ? "← " : d === "out" ? "→ " : "");
  return { pending: n.cards || [],
    relationships: connected.map((r) => ({ name: r.name || r.cid, peer: r.peer || "" })),
    grants: connected.filter((r) => (r.grants || []).length).map((r) => ({ cid: r.cid, name: r.name || r.cid, items: r.grants.map((g) => g.item) })),
    recent: (n.recent || []).slice(0, 15).map((e) => ({ text: arrow(e.dir) + (e.label || e.op || "") + (e.item ? " · " + e.item : ""), who: name(e.cid) })) };
}
