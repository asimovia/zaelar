// ElsewhereChips — what the agent did on ANOTHER screen, as one tap away (V2-792: one agent, many screens).
//
// The desktop and the phone are the same agent and the same conversation, so a report asked for on the phone is
// this screen's business too — but opening it HERE, over whatever is on this screen, is the failure V2-792 removes.
// So the card opens where it was asked for, and every other screen gets a quiet chip: what it is, where it is, and
// one button to have it here. A card that plays (video, music) lives on one screen at a time, and its chip says so.
//
// SHARED by both shells (desktop `system-surfaces.js`, phone `mobile-surfaces.js`); its CSS is in
// `core/shared-surfaces.css`; every word is an i18n key; the logic is `services/screens.js`.
import { h } from "../core/dom.js?v=2";
import * as store from "../core/store.js?v=2";
import { t } from "../core/i18n.js?v=1";
import * as screens from "../services/screens.js?v=1";

const host = () => window.__zaelarDesktop || null;

export function ElsewhereChips() {
  const row = (chip) => {
    const words = screens.chipText(t, chip);
    return h("div", { class: "ew-chip ew-" + chip.why, role: "status" },
      h("span", { class: "ew-mark", "aria-hidden": "true" }, chip.why === "opened" ? "📄" : "▶"),
      h("span", { class: "ew-line" }, words.line),
      h("button", { class: "ew-go", onClick: () => { const hs = host(); if (hs) screens.bringHere(hs, chip); } }, words.action),
      h("button", { class: "ew-x", "aria-label": t("screens.dismiss"), onClick: () => screens.dismiss(chip.key) }, "✕"),
    );
  };
  return h("div", { class: () => "ew-stack" + (store.elsewhere().length ? " on" : "") },
    () => store.elsewhere().map(row));
}
