// ============================================================================
// FeedbackSheet.js — the feedback form in a sheet of its OWN, opened by the dock's ⚠ button (2026-10-25).
//
// It used to live at the bottom of the ☰ menu, and the dock button opened the whole menu and scrolled down to it.
// The operator: there is already a button just for feedback, so the menu must not carry it. One gesture, one sheet:
// the value of this feature (V2-100) is that reporting takes a single tap.
//
// The form itself is FeedbackForm.js, unchanged — at parity with the desktop panel and on its same services. Its
// `open` signal is this sheet's state, so the Sent list refreshes only while the sheet is up.
// ============================================================================

import { h } from "../../../app/core/dom.js?v=2";
import * as store from "../../../app/core/store.js?v=2";
import { t } from "../../../app/core/i18n.js?v=1";
import { FeedbackForm } from "./FeedbackForm.js?v=1";

export function FeedbackSheet() {
  const open = store.mobileFeedbackOpen;
  return h("section", {
    class: () => "zm-sheet zm-feedback" + (open() ? " open" : ""),
    "aria-hidden": () => (open() ? "false" : "true"),
  },
    h("header", { class: "zm-sheet-h" },
      h("div", { class: "zm-sheet-grab" }),
      h("h2", null, () => t("feedback.title")),
      h("button", { class: "zm-sheet-x", "aria-label": () => t("desktop.close"),
        onClick: () => store.setMobileFeedbackOpen(false) }, "×"),
    ),
    h("div", { class: "zm-rows" }, FeedbackForm(() => open())),
  );
}
