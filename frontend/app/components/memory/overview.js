// ============================================================================
// memory/overview.js — the «Overview» tab (V2-808): one card per store with its total, a one-line breakdown, a
// fill bar and a growth note, plus what THIS device is allowed to draw and the last 30 days of growth.
// Every number comes from `/api/memory/viewer/stats`: COUNTs on the server, never the length of a list.
// ============================================================================
import { h } from "../../core/dom.js?v=2";
import * as api from "../../services/api.js?v=2";
import { t } from "../../core/i18n.js?v=1";
import { num, bytes, ago, date, label } from "./format.js?v=1";

// The accent of each store's card: a palette token, so a profile swap repaints it.
const ACCENT = { facts: "--hb-accent", conversation: "--hb-accent", messages: "--hb-accent2", files: "--hb-warn",
                 contacts: "--hb-ok", agenda: "--hb-risk", apps: "--hb-muted", rules: "--hb-accent",
                 phrases: "--hb-accent2", events: "--hb-muted", vault: "--hb-risk" };

// The tab a card opens; a store without its own list has none and its card is not a button.
const TAB_OF = { facts: "facts", conversation: "conversation", messages: "messages", files: "files", apps: "apps",
                 rules: "system", phrases: "system", events: "system", vault: "system" };

function detail(s) {
  const p = s.parts || {};
  switch (s.key) {
    case "facts": return t("memory.store_facts_detail", { concepts: num(p.concepts), relations: num(p.relations) });
    case "conversation": return t("memory.store_conversation_detail")
      + (s.since ? " · " + t("memory.store_conversation_since", { date: date(s.since) }) : "");
    case "messages": return [...Object.entries(p).sort((a, b) => b[1] - a[1])
      .map(([k, v]) => `${label("memory.platform_", k) || t("memory.platform_other")} ${num(v)}`), bytes(s.bytes)].join(" · ");
    case "files": return t("memory.store_files_detail", { images: num(p.images), videos: num(p.videos),
                                                          audio: num(p.audio), documents: num(p.documents) })
      + " · " + bytes(s.bytes);
    case "agenda": return t("memory.store_agenda_detail", { meetings: num(p.meetings), todo: num(p.todo), errands: num(p.errands) });
    case "apps": return s.pending ? t("memory.store_apps_measuring")
      : [...Object.entries(p).map(([k, v]) => `${k === "results" ? t("memory.apps_results", { n: num(s.sheets) })
          : (label("widgets.", k + ".name") || t("memory.app_unnamed"))} ${bytes(v)}`)].join(" · ");
    case "phrases": return t("memory.store_phrases_detail", { paraphrases: num(p.paraphrases) });
    default: return t(`memory.store_${s.key}_detail`);
  }
}

const total = (s) => (s.key === "apps" ? (s.pending ? "…" : bytes(s.total)) : num(s.total));

function note(s) {
  if (s.key === "vault") return { text: t("memory.note_encrypted"), cls: "" };
  if (s.week) return { text: t("memory.note_week", { n: num(s.week) }), cls: "is-growing" };
  if (s.key === "messages" || s.key === "files") return { text: t("memory.note_paged"), cls: "" };
  return { text: t("memory.note_stable"), cls: "is-ok" };
}

export function Overview({ tier, env, goTo }) {
  let grid, sub, spark, sparkLine, timer = null;
  const fillOf = (s, max) => (s.total ? Math.max(3, (Math.log10(Number(s.total) + 1) / Math.log10(max + 1)) * 100) : 0);

  async function load() {
    const body = await api.memoryViewer("stats");
    if (!body) { sub.textContent = t("memory.load_error"); return; }
    const stores = body.stores || [];
    const max = Math.max(1, ...stores.filter((s) => s.key !== "apps").map((s) => Number(s.total) || 0));
    const size = stores.reduce((a, s) => a + (Number(s.bytes) || 0) + (s.key === "apps" ? Number(s.total) || 0 : 0), 0);
    sub.textContent = t("memory.ov_sub", { size: bytes(size), n: num(stores.length), ago: ago(body.counted_at) });
    grid.replaceChildren(...stores.map((s) => {
      const nt = note(s);
      const fill = s.key === "apps" ? (s.total ? 60 : 0) : fillOf(s, max);
      const tab = TAB_OF[s.key];
      return h(tab ? "button" : "div", { class: "hb-card mv-store" + (tab ? " hb-card--interactive" : ""),
                           type: tab ? "button" : null, "data-store": s.key,
                           style: { "--mv-accent": `var(${ACCENT[s.key] || "--hb-accent"})` },
                           onClick: tab ? () => goTo(tab) : null },
        h("span", { class: "mv-store-head" }, h("span", { class: "mv-store-name" }, t(`memory.store_${s.key}`)),
          h("i", { class: "mv-store-dot" })),
        h("span", { class: "mv-store-total" }, total(s)),
        h("span", { class: "mv-store-detail" }, detail(s)),
        h("span", { class: "mv-fill" }, h("i", { style: { width: fill + "%" } })),
        h("span", { class: "mv-store-note " + nt.cls }, nt.text));
    }));
    const g = body.growth || [];
    const vals = g.map((d) => (d.memories || 0) + (d.messages || 0));
    const gmax = Math.max(1, ...vals);
    spark.replaceChildren(...vals.map((v) => h("i", { style: { height: Math.max(3, (v / gmax) * 100) + "%" } })));
    sparkLine.textContent = t("memory.growth_line", { messages: num(g.reduce((a, d) => a + (d.messages || 0), 0)),
                                                      memories: num(g.reduce((a, d) => a + (d.memories || 0), 0)) });
    clearTimeout(timer);
    if (stores.some((s) => s.pending)) timer = setTimeout(load, 2500);   // the app folders are still being measured
  }

  const screen = t(`memory.dev_screen_${tier.tier}`);
  const mem = env.deviceMemory ? t("memory.dev_mem", { n: num(env.deviceMemory) }) : t("memory.dev_mem_unknown");
  const el = h("div", { class: "mv-overview" },
    h("main", { class: "mv-ov-main" },
      h("div", { class: "mv-ov-title" }, h("h2", {}, () => t("memory.ov_title")), h("p", { class: "mv-muted", ref: (x) => (sub = x) })),
      h("div", { class: "mv-stores", ref: (x) => (grid = x) })),
    h("aside", { class: "mv-device", "aria-label": () => t("memory.dev_title") },
      h("div", {},
        h("p", { class: "hb-sectitle" }, () => t("memory.dev_title")),
        h("p", { class: "mv-device-line" }, t("memory.dev_line", { mem, cores: num(env.hardwareConcurrency || 0), screen })),
        h("p", { class: "mv-muted" }, () => t("memory.dev_note"))),
      h("dl", { class: "mv-device-budget" },
        h("dt", {}, () => t("memory.dev_nodes")), h("dd", {}, t("memory.dev_nodes_val", { n: num(tier.nodes) })),
        h("dt", {}, () => t("memory.dev_rows")), h("dd", {}, num(tier.rows)),
        h("dt", {}, () => t("memory.dev_messages")), h("dd", {}, () => t("memory.dev_messages_val")),
        h("dt", {}, () => t("memory.dev_photos")), h("dd", {}, t("memory.dev_photos_val", { n: num(60) })),
        h("dt", {}, () => t("memory.dev_count")), h("dd", {}, () => t("memory.dev_count_val"))),
      h("div", { class: "hb-panel mv-growth" },
        h("p", { class: "hb-panel-title" }, () => t("memory.growth_title")),
        h("div", { class: "mv-spark", ref: (x) => (spark = x) }),
        h("p", { class: "mv-muted", ref: (x) => (sparkLine = x) })),
      h("p", { class: "mv-muted" }, () => t("memory.ov_footer"))));

  let loaded = false;
  return { el, activate() { if (!loaded) { loaded = true; load(); } }, deactivate() {}, refresh() { if (loaded) load(); } };
}
