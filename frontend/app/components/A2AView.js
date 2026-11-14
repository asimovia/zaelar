// ============================================================================
// A2AView.js — the owner's A2A surfaces on the chat wall (V2-866 F3).
//
// Three things, all read from the engine, none decided here:
//   * a CONSENT CARD in the conversation (`a2a.card_request` / `a2a.card_propose`): his Yes / No is one
//     `POST /api/a2a/cards/{id}` — the engine runs the accept / decline / connect / never;
//   * a CONTACT'S MESSAGE (`a2a.message`, trust=contact): drawn apart from the agent's own lines, as plain text
//     (never markdown, never a link the page builds) and labelled as what it is — DATA from a friend's agent,
//     never an order to his;
//   * the NETWORK tab: `GET /api/a2a/network` — pending requests, connected agents, what he shares with each
//     (Stop sharing = the contacts widget's `a2a_revoke`), recent activity. A2A off → the route 404s and the
//     tab is not drawn at all (`on()`).
// ============================================================================

import { h } from "../core/dom.js?v=2";
import { createSignal } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import { t } from "../core/i18n.js?v=1";

const [net, setNet] = createSignal(null);       // the last /api/a2a/network answer; null = off or unknown
export const on = () => Array.isArray((net() || {}).relationships);   // a real answer, never a stub `{}`
const answered = new Map();                     // card id → "yes" | "no" | "error", for the rows already drawn

/** Re-read the network. A 404 is A2A OFF (the routes are absent), which hides the tab. */
export async function refresh() {
  try {
    const r = await fetch("/api/a2a/network");
    setNet(r.ok ? await r.json() : null);
  } catch (_) { setNet(null); }
  if (!on() && store.chatTab() === "red") store.setChatTab("chat");   // a saved Network tab with A2A off
}

/** An SSE `brain` line of category a2a carrying a card → one chat row (the store keeps it like any other). */
export function a2aEvent(d) {
  const x = d.extra || {};
  store.pushChat({ role: "a2a", key: String(x.i18n || d.label || ""), card: x.card || {}, text: String(d.text || "") });
  refresh();
}

async function answer(id, yes, row) {
  let ok = false;
  try {
    const r = await fetch("/api/a2a/cards/" + encodeURIComponent(id), {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ yes }) });
    ok = r.ok;
  } catch (_) {}
  answered.set(id, ok ? (yes ? "yes" : "no") : "error");
  if (row) row.replaceWith(cardView({ id, ...row._card }));
  refresh();
}

/** A consent card: its question and two buttons, or — once answered — what he answered. */
export function cardView(c, cls = "cw-msg") {
  const done = answered.get(c.id);
  const q = t(c.type === "propose" ? "a2a.card_propose" : "a2a.card_request", { name: c.name || "?" });
  const row = h("div", { class: `${cls} a2a a2a-card`, "data-card": c.id || "" },
    h("div", { class: "cl-q" }, q),
    c.note ? h("div", { class: "a2a-note" }, String(c.note)) : null,
    done
      ? h("div", { class: "a2a-done" }, () => t(done === "error" ? "a2a.failed" : done === "yes" ? "a2a.answered_yes" : "a2a.answered_no"))
      : h("div", { class: "cl-cbtns" },
          h("button", { class: "cl-b on", onClick: () => answer(c.id, true, row) }, () => t(c.type === "propose" ? "a2a.connect" : "a2a.accept")),
          h("button", { class: "cl-b", onClick: () => answer(c.id, false, row) }, () => t(c.type === "propose" ? "a2a.no" : "a2a.decline"))));
  row._card = c;
  return row;
}

/** One chat row of role "a2a": a contact's message or a consent card. */
export function a2aChatView(m, cls = "cw-msg") {
  const c = m.card || {};
  if (m.key === "a2a.message" || c.trust === "contact") {
    return h("div", { class: `${cls} a2a a2a-msg`, "data-trust": "contact" },
      h("div", { class: "cw-msg-from" }, () => "🤝 " + t("a2a.message", { name: c.from || "?" })),
      h("div", { class: "cw-msg-body" }, String(c.text || m.text || "")),     // text node: data, never markup
      h("div", { class: "a2a-note" }, () => t("a2a.not_an_order")));
  }
  return cardView(c, cls);
}

async function revoke(cid, item) {
  try {
    await fetch("/widgets/contactos/action", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "a2a_revoke", payload: { contactId: cid, item } }) });
  } catch (_) {}
  refresh();
}

const section = (key, rows) => h("div", { class: "a2a-sec" },
  h("div", { class: "cn-fam" }, () => t(key)),
  rows.length ? rows : h("div", { class: "cw-empty" }, () => t("a2a.none")));

/** The Network tab's body: four blocks over one read. */
export function networkBody() {
  const n = net() || {};
  const rels = n.relationships || [];
  const name = (cid) => (rels.find((r) => r.cid === cid) || {}).name || cid || "?";
  const connected = rels.filter((r) => r.status === "accepted");
  return [
    section("a2a.pending", (n.cards || []).map((c) => cardView(c, "cl-row"))),
    section("a2a.relationships", connected.map((r) => h("div", { class: "cl-row a2a-rel" },
      h("span", { class: "a2a-name" }, r.name || r.cid), h("span", { class: "ctnote" }, r.peer || "")))),
    section("a2a.grants", connected.filter((r) => (r.grants || []).length).map((r) => h("div", { class: "cl-row a2a-share" },
      h("span", { class: "a2a-name" }, r.name || r.cid),
      ...(r.grants || []).map((g) => h("span", { class: "a2a-chip" }, g.item,
        h("button", { class: "cl-b", title: () => t("a2a.stop_sharing"), onClick: () => revoke(r.cid, g.item) }, "✕")))))),
    section("a2a.recent", (n.recent || []).slice(0, 15).map((e) => h("div", { class: "cl-row a2a-ev" },
      h("span", null, (e.dir === "in" ? "← " : e.dir === "out" ? "→ " : "") + (e.label || e.op || "") + (e.item ? " · " + e.item : "")),
      h("span", { class: "ctnote" }, name(e.cid))))),
  ];
}
