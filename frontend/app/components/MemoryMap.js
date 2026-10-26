// ============================================================================
// MemoryMap — the 🧠 memory viewer (V2-808, V2-814): a full-screen overlay that MONITORS the brain.
//
//   Overview · Graph
//
// A monitor, not a browser: the overview totals every store the agent keeps (each card opens to its last 30 days
// and its breakdown), the graph shows how the memory relates concepts. No stored row — a fact, a turn of the
// conversation, a message, a file — is ever listed here, and nothing about the machine is ever printed. What the
// canvas draws is still bounded by what THIS device can draw (memory/budget.js); that bound is internal.
// Toggled by the 🧠 icon (store.memOpen); the tabs build lazily on first visit.
//
// LIVE: `memory.updated` (bridged by the server onto SSE) bumps store.memBump and carries the touched ids in
// store.memPulse. While open, the visible tab is asked to `refresh()` — the graph re-aggregates (bounded) and keeps
// its node positions — and the graph rings the touched memories for a few seconds. Nothing refetches while closed.
// ============================================================================
import { h, raw } from "../core/dom.js?v=2";
import { createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as api from "../services/api.js?v=2";
import { CLOSE_ICON } from "../lib/icons.js?v=1";
import { t } from "../core/i18n.js?v=1";
import { currentTier } from "./memory/budget.js?v=1";
import { Overview } from "./memory/overview.js?v=2";
import { GraphView } from "./memory/graph-view.js?v=2";

const TABS = ["overview", "graph"];

function ensureStyles() {
  const href = new URL("./memory/memory-viewer.css?v=2", import.meta.url).href;
  if ([...document.querySelectorAll("link[rel=stylesheet]")].some((l) => l.href === href)) return;
  const l = document.createElement("link");
  l.rel = "stylesheet"; l.href = href;
  document.head.append(l);
}

export function MemoryMap() {
  ensureStyles();
  const tier = currentTier();
  const views = {};
  let current = "", bodyEl, tabsEl, bumpT = null;

  const make = (tab) => (tab === "graph" ? GraphView({ tier }) : Overview({ goTo: show }));

  async function show(tab) {
    if (!TABS.includes(tab)) tab = "overview";
    if (current && views[current]) { views[current].deactivate(); views[current].el.hidden = true; }
    current = tab;
    tabsEl.querySelectorAll(".hb-tab").forEach((b) => {
      const on = b.dataset.tab === tab;
      b.classList.toggle("is-on", on); b.setAttribute("aria-selected", String(on));
    });
    if (!views[tab]) {
      views[tab] = make(tab);
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
