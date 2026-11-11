// AppsPane.js — the APPS page (V2-876 D-C, operator 2026-11-11: «un icono abajo para acceder a las apps, con todos los
// iconos»): the dock's Apps button opens a full-screen grid of every app — ITS icon, its name, one line of what it does
// — and a tap opens it on the deck through `hb:open-card`, the door every opener uses. The list is the registry's user
// apps (apps-catalog.js reads the same); the line is the app's own `widgets.<id>.about` string in his language, absent
// for an app that has none. An app's icon is its manifest's `icon` when the registry carries one, else its monogram on
// its own colour — the same tile the deck's home draws, so an app looks the same on both screens. Never one glyph for all.
import { h } from "../../../app/core/dom.js?v=2";
import { createSignal, createEffect } from "../../../app/core/reactive.js?v=2";
import * as store from "../../../app/core/store.js?v=2";
import * as api from "../../../app/services/api.js?v=2";
import { t } from "../../../app/core/i18n.js?v=1";
import { tileHue } from "./Deck.js?v=5";
import { Page } from "./Page.js?v=1";

export const [appsOpen, setAppsOpen] = createSignal(false);

const line = (id) => { const k = "widgets." + id + ".about", s = t(k); return s === k ? "" : s; };

export function AppsPane() {
  const [rows, setRows] = createSignal(null);
  // Read afresh each time the page comes up: an app generated a minute ago belongs on it.
  createEffect(() => {
    if (!appsOpen()) return;
    api.getWidgetsRegistry().then((r) => setRows(((r && r.registry) || [])
      .filter((w) => w && w.surface === "user" && w.id)
      .sort((a, b) => String(a.name || a.id).localeCompare(String(b.name || b.id))))).catch(() => setRows([]));
  });
  const open = (id) => {
    try { document.dispatchEvent(new CustomEvent("hb:open-card", { detail: { id, by: "hand" } })); } catch (_) {}
    setAppsOpen(false);
    api.uiEvent("mobile:app_open", { id });
  };
  // Two apps never wear the same tile: the same letter on the same colour moves that colour on (rare: a hash clash).
  let used = new Set();
  const tile = (w) => {
    const glyph = w.icon ? String(w.icon) : String(w.name || w.id).trim().charAt(0).toUpperCase();
    let hue = tileHue(w.id);
    while (used.has(glyph + hue)) hue = (hue + 47) % 360;
    used.add(glyph + hue);
    return h("button", { class: "zm-app", "data-app": w.id, onClick: () => open(w.id) },
    h("span", { class: "zm-app-ic", style: { "--tile": `hsl(${hue} 62% 46%)` } }, glyph),
    h("b", null, w.name || w.id),
    line(w.id) ? h("small", null, line(w.id)) : null);
  };

  return Page({ id: "apps", open: appsOpen, title: () => t("mobile.apps"), close: () => setAppsOpen(false) },
    h("div", { class: "zm-apps-grid", role: "list" }, () => {
      const all = rows(); used = new Set();
      if (!all) return h("div", { class: "hb-empty-state" }, t("appsWin.loading"));
      if (!all.length) return h("div", { class: "hb-empty-state" }, t("appsWin.empty"));
      const sys = all.filter((w) => w.origin === "builtin"), mine = all.filter((w) => w.origin !== "builtin");
      return [...sys.map(tile), ...(mine.length ? [h("div", { class: "zm-apps-sec" }, t("mobile.apps_mine")), ...mine.map(tile)] : [])];
    }));
}
