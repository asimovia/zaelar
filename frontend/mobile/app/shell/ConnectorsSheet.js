// ConnectorsSheet.js — ☰ → Connectors, a full-screen page (2026-11-16, the unified menu). The list is the desktop chat
// panel's own column (`frontend/side/conectores/`, through services/conectores-bridge.js): what he can connect with its
// state, then the wishlist with «I want it».
// Connecting holds a credential form, which lives in the desktop's settings panel (V2-520: a list never holds one):
// «Connect» opens THAT panel on this connector, this once — `?config=conectores&connector=<id>&back=m` is not a shell
// choice (index.html does not persist it) and closing the panel brings him back to the phone (app/main.js).
import * as store from "../../../app/core/store.js?v=2";
import { createSignal } from "../../../app/core/reactive.js?v=2";
import { t } from "../../../app/core/i18n.js?v=1";
import { mountConectores } from "../../../app/services/conectores-bridge.js?v=1";
import { Page } from "./Page.js?v=1";

// The page's own open signal, as AppsPane's: only this shell has the page, so the shared store does not carry it.
export const [connectorsOpen, setConnectorsOpen] = createSignal(false);

export function ConnectorsSheet() {
  const open = connectorsOpen, close = () => setConnectorsOpen(false);
  const host = document.createElement("div");             // re-read on every visit: he may have connected one meanwhile
  mountConectores(host, { visible: open, manage: (id) => location.assign(
    "/?config=conectores&back=m&connector=" + encodeURIComponent(String(id || ""))) });
  return Page({ id: "connectors", open, title: () => t("chat.tabConnectors"), close,
    back: () => { close(); store.setMobileMenuOpen(true); } }, host);
}
