// ConnectorsList.js — every connector by category: what he CAN connect (live, `connectors/registry.py`'s descriptors(),
// with its state) and, folded below, what we do not have yet (the catalog's planned / not-possible wishlist, with «I
// want it»). ONE list for both shells (2026-11-16): the desktop chat wall's «Connectors» tab and the phone's ☰ →
// Connectors page draw it from the same two reads, so they can never disagree about what is connected. `onManage(id)`
// is the shell's door to the CREDENTIAL surface — the list itself never holds a form (V2-520: voice and lists carry
// intention, never a credential).
import { h } from "../core/dom.js?v=2";
import { createSignal } from "../core/reactive.js?v=2";
import * as api from "../services/api.js?v=2";
import * as feedbackApi from "../services/feedback-api.js?v=1";
import { t } from "../core/i18n.js?v=1";
import { groupGoogle } from "./ConnectorWizard.js?v=7";

// Families in the order he expects them; anything not listed sorts after, alphabetically. A test walks the live
// descriptors() against this array (a family missing here files his calendar under Infraestructura, silently).
const CONN_FAMILY_ORDER = ["google", "mensajeria", "musica", "fotos", "archivos", "video", "agenda", "contactos", "infra"];
const connFamilyRank = (f) => { const i = CONN_FAMILY_ORDER.indexOf(f); return i < 0 ? 99 : i; };

export function ConnectorsList({ onManage = () => {} } = {}) {
  const openConnectorConfig = (id) => onManage(id);
  const [connCatalog, setConnCatalog] = createSignal({ live: [], wish: [] });
  const [connRequested, setConnRequested] = createSignal(new Set());
  // A failed read (the engine still booting) used to be painted as «no connectors» and never retried —
  // the operator opened the tab, saw it empty, and only the wishlist came back later. Retried a few times.
  const refreshConnectors = async (tries = 6) => {
    const [live, wish] = await Promise.all([api.getConnectors(), api.getConnectorCatalog()]);
    const rows = (live && live.connectors) || [];
    setConnCatalog({ live: groupGoogle(rows), wish: (wish && wish.catalog) || [] });
    if (!rows.length && tries > 1) setTimeout(() => refreshConnectors(tries - 1), 2000);
  };
  // "Lo quiero" on a PLANNED entry: a request the receiving side can COUNT, so it carries the manifest `id`
  // as a fixed, machine-written prefix rather than anything the operator typed — free text cannot be
  // grouped. Once per session per id (the row itself shows it was sent instead of inviting a second click).
  const requestConnector = async (m) => {
    if (connRequested().has(m.id)) return;
    setConnRequested(new Set([...connRequested(), m.id]));
    try { await feedbackApi.sendFeedback({ message: `[conector:${m.id}] Lo quiero: ${m.label}` }); }
    catch (_) { /* best-effort; the row already reflects the attempt and nothing here blocks the tab */ }
  };

  // One row per connector he CAN use, with the one button that matters: connect it, or manage it. Google is
  // one row (one account, a consent per service — the count says how many are on).
  const connLiveRow = (c) => {
    const n = c.services ? c.services.filter(x => x.connected).length : 0;
    const on = c.services ? n > 0 : c.connected;
    return h("div", { class: "cl-row" },
      h("div", { class: "cl-main" },
        h("div", { class: "cl-name" }, h("span", { class: () => "cl-dot" + (on ? " on" : "") }), c.label || c.id),
        h("div", { class: "cl-meta" }, () => c.services ? t("config.cx.of_services", { n, total: c.services.length })
                                                       : (c.connected ? t("chat.connected") : t("chat.disconnected"))),
      ),
      h("div", { class: "cl-btns" },
        h("button", { class: "cl-b" + (on ? "" : " on"), onClick: () => openConnectorConfig(c.id) },
          () => t(on ? "chat.manageBtn" : "chat.connectBtn")),
      ),
    );
  };

  const connWishRow = (m) => {
    const impossible = m.state === "not-possible";
    const requested = connRequested().has(m.id);
    return h("div", { class: "cl-row" + (impossible ? " cn-imposs" : ""), title: impossible  // pack `ui` key; the manifest's sentence only for an entry with no key yet
        ? ((k) => t(k) !== k ? t(k) : (m["why-not"] || ""))("connectors." + m.id + ".why_not") : "" },
      h("div", { class: "cl-main" },
        h("div", { class: "cl-name" }, h("span", { class: "cl-dot" }), m.label || m.id),
        h("div", { class: "cl-meta" },
          impossible ? t("chat.connWishlistImpossible") : t("chat.connWishlistPlanned")),
      ),
      h("div", { class: "cl-btns" },
        impossible ? null
          : h("button", { class: "cl-b" + (requested ? "" : " on"), disabled: requested,
                          onClick: () => requestConnector(m) },
              () => t(requested ? "chat.connWantedBtn" : "chat.connWantBtn")),
      ),
    );
  };

  // What he can connect comes FIRST, by family; what we do not have yet (planned / not possible) goes below,
  // folded, so the list he came for is not buried under a wishlist.
  const byFamily = (rows) => {
    const fams = new Map();
    for (const r of rows) { const f = r.family || "infra"; if (!fams.has(f)) fams.set(f, []); fams.get(f).push(r); }
    return [...fams.keys()].sort((a, b) => connFamilyRank(a) - connFamilyRank(b) || a.localeCompare(b)).map(f => [f, fams.get(f)]);
  };
  // t() returns the KEY itself when a string is missing (truthy) — never `|| fam` here (V2-538).
  const famHead = (fam) => h("div", { class: "cn-fam" }, () => fam === "google" ? "Google" : t("chat.connFamily." + fam));
  const connFamilySections = () => {
    const { live, wish } = connCatalog();
    if (!live.length && !wish.length) return [h("div", { class: "cw-empty" }, () => t("chat.connEmpty"))];
    const out = [];
    for (const [fam, rows] of byFamily(live)) { out.push(famHead(fam)); rows.forEach(c => out.push(connLiveRow(c))); }
    if (wish.length) {
      const inner = [];
      for (const [fam, rows] of byFamily(wish)) { inner.push(famHead(fam)); rows.forEach(m => inner.push(connWishRow(m))); }
      out.push(h("details", { class: "cn-soon" },
        h("summary", { class: "cn-fam" }, () => t("chat.connSoon", { n: wish.length })), ...inner));
    }
    return out;
  };

  return { node: h("div", { class: "cl-list" }, () => connFamilySections()), refresh: refreshConnectors };
}
