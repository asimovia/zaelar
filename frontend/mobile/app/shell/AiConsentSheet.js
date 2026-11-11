// AiConsentSheet.js — the question asked before the first turn inside the native app (ai-consent.js says when).
// What is sent, to whom in general terms, that it can be withdrawn in Settings; Accept or Not now. «Not now» closes
// it and leaves the orb and the send button asking again; nothing else in the app is locked.
import { h } from "../../../app/core/dom.js?v=2";
import { createEffect } from "../../../app/core/reactive.js?v=2";
import { t } from "../../../app/core/i18n.js?v=1";
import * as consent from "./ai-consent.js?v=1";
import { Page } from "./Page.js?v=1";

export function AiConsentSheet() {
  // The orb and the send button look disabled while the yes is missing (they still open this sheet when tapped).
  createEffect(() => document.documentElement.classList.toggle("zm-consent-pending", consent.pending()));
  return Page({ id: "consent", open: consent.sheetOpen, title: () => t("consent.title"), close: () => consent.setSheetOpen(false),
    attrs: { role: "dialog", "aria-modal": "true" } },
    h("div", { class: "zm-consent-b" },
      h("p", null, () => t("consent.body")),
      h("p", null, () => t("consent.what")),
      h("p", { class: "zm-consent-note" }, () => t("consent.withdraw_note")),
    ),
    h("div", { class: "zm-consent-a" },
      h("button", { class: "zm-primary", onClick: () => consent.decide(true) }, () => t("consent.accept")),
      h("button", { class: "zm-ghost", onClick: () => consent.setSheetOpen(false) }, () => t("consent.later")),
    ),
  );
}
