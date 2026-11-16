// config-link.js — `/?config=<tab>&connector=<id>&back=m`: the desktop's settings panel opened by a LINK (2026-11-16).
// The phone's ☰ → Connectors «Connect» lands here: the credential form lives in this panel (V2-520: a list never holds
// one), so the phone opens it for ONE connector, and with `back=m` closing it goes back to the phone. index.html does
// not take `config` as a shell choice, so this is never a sticky switch to the desktop. Imported by system-surfaces.js
// (the desktop's surface list, which is where the panel itself is declared).
import { createEffect } from "./reactive.js?v=2";
import * as store from "./store.js?v=2";
import { t } from "./i18n.js?v=1";

(function () {
  const q = new URLSearchParams(location.search), tab = q.get("config");
  if (!tab) return;
  const back = q.get("back") === "m";
  setTimeout(() => {
    document.dispatchEvent(new CustomEvent("hb:open-config", { detail: { tab, connector: q.get("connector") || "",
      from: back ? t("chat.tabConnectors") : "" } }));
    if (back) { let was = false; createEffect(() => { if (store.configOpen()) was = true; else if (was) location.replace("/m"); }); }
  }, 700);
})();
