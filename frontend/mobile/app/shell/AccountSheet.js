// AccountSheet.js — ☰ → My account, a full-screen page (2026-11-17, operator: the ☰ page is opened many times a day, so
// what is done once — deleting the account, reading an invoice — goes one tap deeper, here). Every row opens the
// account page the engine names (V2-785) at one of its sections, in a new window: inside the native app that is the
// system browser, so nothing here is a purchase surface. Cloud only: on self-host there is no account behind it and
// the ☰ page does not offer this page at all.
import { h } from "../../../app/core/dom.js?v=2";
import * as store from "../../../app/core/store.js?v=2";
import { createSignal } from "../../../app/core/reactive.js?v=2";
import { t } from "../../../app/core/i18n.js?v=1";
import { accountLink } from "../../../app/core/account-link.js?v=1";
import { inNativeApp } from "../../../app/core/native.js?v=1";
import { HOME_ICON, USER_ICON, DOCS_ICON, LIST_ICON, TRASH_ICON } from "../../../app/lib/icons.js?v=2";
import { Page } from "./Page.js?v=1";
import { Row } from "./menu-row.js?v=1";

// The page's own open signal, as ConnectorsSheet's: only this shell has the page.
export const [accountOpen, setAccountOpen] = createSignal(false);

/** Open the account page at `section` ("" = its overview). V2-785: the engine's url, never a relative "/account". */
export function openAccount(section = "") {
  const u = accountLink(store.accountUrl(), section);
  if (u) window.open(u, "_blank", "noopener");
}

export function AccountSheet() {
  const close = () => setAccountOpen(false);
  // Plans and invoices are the account's billing. Inside the native app they are not offered (V2-870: the app sells
  // nothing and links to no purchase); the account page itself stays one row away for everything else.
  const billing = () => !inNativeApp();
  return Page({ id: "account", open: accountOpen, title: () => t("mobile.account"), close,
    back: () => { close(); store.setMobileMenuOpen(true); } },
    h("div", { class: "zm-rows" },
      Row(HOME_ICON, () => t("mobile.account_open"), () => t("mobile.account_open_sub"), () => openAccount()),
      Row(USER_ICON, () => t("mobile.account_profile"), () => t("mobile.account_profile_sub"), () => openAccount("profile")),
      () => billing() ? Row(LIST_ICON, () => t("mobile.account_plans"), () => t("mobile.account_plans_sub"), () => openAccount("plans")) : null,
      () => billing() ? Row(DOCS_ICON, () => t("mobile.account_billing"), () => t("mobile.account_billing_sub"), () => openAccount("billing")) : null,
      // App Review 5.1.1(v) and Play's account-deletion rule: deletion starts inside the app. It lives here, one tap
      // under My account, not on the ☰ page (operator, 2026-11-17).
      Row(TRASH_ICON, () => t("mobile.delete_account"), () => t("mobile.delete_account_sub"), () => openAccount("delete"), "danger"),
    ),
  );
}
