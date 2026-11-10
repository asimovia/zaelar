// ProfileMenu.js — the 👤 at the RIGHT end of the top bar and its small menu (operator, 2026-11-10: the profile
// icon goes last, and clicking it opens a menu with «Private area» and «Log out»).
//
// Both destinations belong to the DEPLOYMENT and arrive from /api/config: `account_url` (the account page, opened in
// a new tab — what the old account panel's only button did) and `logout_url` (env `ZAELAR_LOGOUT_URL`, navigated in
// this tab: that page ends the session and lands on the deployment's login). An item whose url is unset is not drawn,
// and with neither there is no icon at all: a self-hosted engine has no account page and no login to leave.
import { h, raw } from "../core/dom.js?v=2";
import * as store from "../core/store.js?v=2";
import * as api from "../services/api.js?v=2";
import { t } from "../core/i18n.js?v=1";
import { USER_ICON } from "../lib/icons.js?v=2";
import { accountLink } from "../core/account-link.js?v=1";

/** The menu's items, in order, for the urls the deployment named — the decision the rendered test reads. Pure. */
export function profileItems(accountUrl, logoutUrl) {
  const items = [];
  const account = accountLink(accountUrl);
  if (account) items.push({ id: "account", label: "topbar.profile.account", href: account, newTab: true });
  const logout = String(logoutUrl || "").trim();
  if (logout) items.push({ id: "logout", label: "topbar.profile.logout", href: logout, newTab: false });
  return items;
}

export function ProfileMenu() {
  const items = () => profileItems(store.accountUrl(), store.logoutUrl());
  const close = () => store.setAccountOpen(false);
  let wrap = null;
  // A press outside the menu, or Escape, closes it: a menu that only its own button can close stays over the canvas.
  document.addEventListener("pointerdown", (e) => { if (store.accountOpen() && wrap && !wrap.contains(e.target)) close(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && store.accountOpen()) close(); });
  const item = (it) => h("a", {
    class: "pm-item", role: "menuitem", "data-item": it.id, href: it.href,
    target: it.newTab ? "_blank" : null, rel: it.newTab ? "noopener" : null,
    onClick: () => { api.uiEvent("topbar:profile", { item: it.id }); close(); },
  }, () => t(it.label));
  return () => {
    const list = items();
    if (!list.length) { wrap = null; return null; }
    wrap = h("div", { class: "pm" },
      h("button", {
        class: () => "ic" + (store.accountOpen() ? " on" : ""), id: "acctBtn", title: () => t("topbar.account.title"),
        "aria-haspopup": "menu", "aria-expanded": () => (store.accountOpen() ? "true" : "false"),
        onClick: () => { const v = !store.accountOpen(); store.setAccountOpen(v); api.uiEvent("topbar:account", { state: v ? "open" : "close" }); },
      }, raw(USER_ICON)),
      h("div", { class: () => "pm-menu" + (store.accountOpen() ? " on" : ""), role: "menu" }, ...list.map(item)),
    );
    return wrap;
  };
}
