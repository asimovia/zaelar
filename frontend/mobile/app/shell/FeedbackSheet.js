// FeedbackSheet.js — the feedback form as a full-screen page (V2-876 D-C): reached from a row of the ☰ menu (it left
// the dock), its ‹ goes back to the menu. The form is FeedbackForm.js — at parity with the desktop panel, its two quick
// thumbs included; its `open` signal is this page's, so the Sent list refreshes only while the page is up.
import * as store from "../../../app/core/store.js?v=2";
import { t } from "../../../app/core/i18n.js?v=1";
import { FeedbackForm } from "./FeedbackForm.js?v=2";
import { Page } from "./Page.js?v=1";

export function FeedbackSheet() {
  const open = store.mobileFeedbackOpen, close = () => store.setMobileFeedbackOpen(false);
  return Page({ id: "feedback", open, title: () => t("feedback.title"), close,
    back: () => { close(); store.setMobileMenuOpen(true); } }, FeedbackForm(() => open(), close));
}
