// ============================================================================
// MemoryMap — the 🧠 memory viewer (V2-808): a full-screen overlay with ONE TAB PER STORE.
//
//   Overview · Graph · Facts · Conversation · Messages · Files · Apps · System
//
// Every store the agent keeps is shown and totalled, and none is ever loaded whole: totals are COUNTs on the
// server (`/api/memory/viewer/stats`), every list arrives one capped page at a time, newest first, and the graph is
// aggregated on the server and bounded by what THIS device can draw (memory/budget.js). Toggled by the 🧠 icon
// (store.memOpen); the tabs build lazily on first visit.
//
// LIVE, AS DELTAS: `memory.updated` (bridged by the server onto SSE) bumps store.memBump and carries the touched
// ids in store.memPulse. While open, the visible tab is asked to `refresh()` — the graph re-aggregates (bounded)
// and keeps its node positions, the lists prepend only the rows they do not show yet — and the graph rings the
// touched memories for a few seconds. Nothing refetches while the viewer is closed.
// ============================================================================
import { h, raw } from "../core/dom.js?v=2";
import { createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as api from "../services/api.js?v=2";
import { CLOSE_ICON } from "../lib/icons.js?v=1";
import { t } from "../core/i18n.js?v=1";
import { currentEnv, deviceTier } from "./memory/budget.js?v=1";
import { num } from "./memory/format.js?v=1";
import { Overview } from "./memory/overview.js?v=1";
import { GraphView } from "./memory/graph-view.js?v=1";
import { FactsList, ConversationList, MessagesList, FilesList, AppsList, SystemList } from "./memory/lists.js?v=1";

const TABS = ["overview", "graph", "facts", "conversation", "messages", "files", "apps", "system"];

function ensureStyles() {
  const href = new URL("./memory/memory-viewer.css?v=1", import.meta.url).href;
  if ([...document.querySelectorAll("link[rel=stylesheet]")].some((l) => l.href === href)) return;
  const l = document.createElement("link");
  l.rel = "stylesheet"; l.href = href;
  document.head.append(l);
}

export function MemoryMap() {
  ensureStyles();
  const env = currentEnv();
  const tier = deviceTier(env);
  const views = {};
  let current = "", bodyEl, tabsEl, platforms = null, bumpT = null;

  async function knownPlatforms() {
    if (platforms) return platforms;
    const s = await api.memoryViewer("stats");
    const m = (s?.stores || []).find((x) => x.key === "messages");
    platforms = Object.keys(m?.parts || {});
    return platforms;
  }

  function systemHead() {
    const box = h("div", { class: "mv-sys-head" });
    api.memoryViewer("stats").then((s) => {
      const get = (k) => (s?.stores || []).find((x) => x.key === k)?.total || 0;
      box.replaceChildren(...["rules", "phrases", "events", "vault"].map((k) => h("span", { class: "hb-badge hb-badge--bare" },
        `${t("memory.store_" + k)} · ${num(get(k))}`)));
    });
    return box;
  }

  async function make(tab) {
    switch (tab) {
      case "overview": return Overview({ tier, env, goTo: show });
      case "graph": return GraphView({ tier });
      case "facts": return FactsList(tier.rows);
      case "conversation": return ConversationList(tier.rows);
      case "messages": return MessagesList(tier.rows, await knownPlatforms());
      case "files": return FilesList();
      case "apps": return AppsList();
      default: return SystemList(tier.rows, systemHead);
    }
  }

  async function show(tab) {
    if (!TABS.includes(tab)) tab = "overview";
    if (current && views[current]) { views[current].deactivate(); views[current].el.hidden = true; }
    current = tab;
    tabsEl.querySelectorAll(".hb-tab").forEach((b) => {
      const on = b.dataset.tab === tab;
      b.classList.toggle("is-on", on); b.setAttribute("aria-selected", String(on));
    });
    if (!views[tab]) {
      views[tab] = await make(tab);
      views[tab].el.dataset.view = tab;
      bodyEl.append(views[tab].el);
    }
    if (current !== tab) return;
    views[tab].el.hidden = false;
    views[tab].activate();
  }

  createEffect(() => {
    const open = store.memOpen();
    if (open) { if (!current) show("overview"); else views[current]?.activate(); }
    else if (current && views[current]) views[current].deactivate();
  });

  // Live deltas — only the visible tab, only while open, debounced: a burst of writes is one refresh.
  createEffect(() => {
    store.memBump();
    if (!store.memOpen()) return;
    clearTimeout(bumpT);
    bumpT = setTimeout(() => views[current]?.refresh(), 1200);
  });
  createEffect(() => {
    const p = store.memPulse();
    if (p && store.memOpen() && views.graph) views.graph.pulse(p.ids || []);
  });

  const close = () => store.setMemOpen(false);
  window.addEventListener("keydown", (e) => { if (e.key === "Escape" && store.memOpen()) close(); });

  return h("div", { class: () => "memmap" + (store.memOpen() ? " open" : ""), role: "dialog",
                    "aria-label": () => t("memory.title") },
    h("header", { class: "mv-head" },
      h("h1", { class: "mv-title" }, () => t("memory.title")),
      h("nav", { class: "hb-tabs mv-tabs", role: "tablist", "aria-label": () => t("memory.tabs_label"), ref: (x) => (tabsEl = x) },
        ...TABS.map((tab) => h("button", { class: "hb-tab", type: "button", role: "tab", "data-tab": tab,
                                           "aria-selected": "false", onClick: () => show(tab) }, () => t("memory.tab_" + tab)))),
      h("button", { class: "hb-iconbtn hb-iconbtn--framed hb-iconbtn--lg mv-close", type: "button",
                    "aria-label": () => t("memory.close"), title: () => t("memory.close"), onClick: close }, raw(CLOSE_ICON))),
    h("div", { class: "mv-body", ref: (x) => (bodyEl = x) }));
}
