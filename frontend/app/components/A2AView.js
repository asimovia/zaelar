// ============================================================================
// A2AView.js — the owner's A2A surfaces on the chat wall (V2-866 F3).
//
// Two things, all read from the engine, none decided here:
//   * a CONSENT CARD in the conversation (`a2a.card_request` / `a2a.card_propose`): the Network column's own card
//     (`cardView`, through services/red-bridge.js), whose Yes / No is one `POST /api/a2a/cards/{id}`;
//   * a CONTACT'S MESSAGE (`a2a.message`, trust=contact): drawn apart from the agent's own lines, as plain text
//     (never markdown, never a link the page builds) and labelled as what it is — DATA from a friend's agent,
//     never an order to his;
// The NETWORK tab is a column of its own (`frontend/side/red/`, wired by services/red-bridge.js, which keeps the read).
// ============================================================================

import { h } from "../core/dom.js?v=2";
import { t } from "../core/i18n.js?v=1";
import { refresh, cardView } from "../services/red-bridge.js?v=1";
import { legacy } from "../services/wall-legacy.js?v=1";

/** An SSE `brain` line of category a2a carrying a card → one box on the chat wall. */
export function a2aEvent(d) {
  const x = d.extra || {};
  legacy.pushChat({ role: "a2a", key: String(x.i18n || d.label || ""), card: x.card || {}, text: String(d.text || "") });
  refresh();
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
