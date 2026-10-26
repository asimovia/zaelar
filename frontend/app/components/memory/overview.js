// ============================================================================
// memory/overview.js — the «Overview» tab (V2-808, V2-814): one card per store the brain keeps, with its total
// and a one-line breakdown. A card opens IN PLACE to show its last 30 days and its breakdown (sources, types,
// sizes). Totals only: no stored row is ever listed, and nothing about the machine is printed.
// Every number comes from `/api/memory/viewer/stats`: COUNTs on the server, never the length of a list.
// ============================================================================
import { h } from "../../core/dom.js?v=2";
import * as api from "../../services/api.js?v=2";
import { t } from "../../core/i18n.js?v=1";
import { num, bytes, ago, date, label } from "./format.js?v=2";

// The accent of each store's card: a palette token, so a profile swap repaints it.
const ACCENT = { memories: "--hb-accent", conversation: "--hb-accent", messages: "--hb-accent2", files: "--hb-warn",
                 contacts: "--hb-ok", agenda: "--hb-risk", apps: "--hb-muted", rules: "--hb-accent",
                 phrases: "--hb-accent2", events: "--hb-muted", vault: "--hb-risk" };
const FILE_TYPES = ["images", "videos", "audio", "documents", "other"];

const sum = (a) => (a || []).reduce((x, y) => x + (Number(y) || 0), 0);
const appName = (a) => (a.key === "results" ? t("memory.apps_results", { n: num(a.sheets) })
  : label("widgets.", a.key + ".name") || a.title || t("memory.app_unnamed"));
const platform = (k) => label("memory.platform_", k) || t("memory.platform_other");

// The big number of a card.
function total(s) {
  if (s.key === "apps") return s.pending ? "…" : bytes(s.total);
  if (s.key === "files") return bytes(s.bytes);
  return num(s.total);
}

// The one line under it.
function detail(s) {
  const p = s.parts || {};
  switch (s.key) {
    case "memories": return t("memory.store_memories_detail", { concepts: num(p.concepts), relations: num(p.relations) });
    case "conversation": return t("memory.store_conversation_detail", { days: num(p.days) })
      + (s.since ? " · " + t("memory.since", { date: date(s.since) }) : "");
    case "messages": return t("memory.store_messages_detail", { per_day: num(Math.round(sum(s.daily) / 30)),
                                                                sources: num(Object.keys(p).length) });
    case "files": {
      const ty = s.types || {};
      return t("memory.store_files_detail", { n: num(s.total), images: num(ty.images?.n), videos: num(ty.videos?.n) });
    }
    case "agenda": return t("memory.store_agenda_detail", { meetings: num(p.meetings), todo: num(p.todo), errands: num(p.errands) });
    case "apps": return s.pending ? t("memory.store_apps_measuring") : t("memory.store_apps_detail", { n: num((s.apps || []).length) });
    case "phrases": return t("memory.store_phrases_detail", { paraphrases: num(p.paraphrases) });
    default: return t(`memory.store_${s.key}_detail`);
  }
}

function note(s) {
  if (s.key === "vault") return { text: t("memory.note_encrypted"), cls: "" };
  const week = s.week ?? (s.daily ? sum(s.daily.slice(-7)) : 0);
  if (week) return { text: t("memory.note_week", { n: num(week) }), cls: "is-growing" };
  return { text: t("memory.note_stable"), cls: "is-ok" };
}

// The rows of the opened card: [label, value, share 0..1].
function breakdown(s) {
  const p = s.parts || {};
  const share = (v, all) => (all ? v / all : 0);
  switch (s.key) {
    case "memories": return [
      [t("memory.level_short_cap"), num(p.short), share(p.short, s.total)],
      [t("memory.level_long_cap"), num(p.long), share(p.long, s.total)],
      [t("memory.part_concepts"), num(p.concepts)], [t("memory.part_relations"), num(p.relations)]];
    case "conversation": return [
      [t("memory.part_sessions"), num(s.total)], [t("memory.part_days"), num(p.days)],
      [t("memory.part_turns"), num(p.turns)]];
    case "messages": {
      const rows = Object.entries(p).sort((a, b) => b[1] - a[1])
        .map(([k, v]) => [platform(k), num(v), share(v, s.total)]);
      return [...rows, [t("memory.part_size"), bytes(s.bytes)]];
    }
    case "files": {
      const ty = s.types || {};
      return FILE_TYPES.filter((k) => ty[k]?.n).sort((a, b) => ty[b].bytes - ty[a].bytes)
        .map((k) => [t("memory.files_" + k), `${num(ty[k].n)} · ${bytes(ty[k].bytes)}`, share(ty[k].bytes, s.bytes)]);
    }
    case "agenda": return [[t("memory.part_meetings"), num(p.meetings)], [t("memory.part_todo"), num(p.todo)],
                           [t("memory.part_errands"), num(p.errands)]];
    case "apps": return (s.apps || []).map((a) => [appName(a), bytes(a.bytes), share(a.bytes, s.total)]);
    case "phrases": return [[t("memory.part_phrases"), num(s.total)], [t("memory.part_paraphrases"), num(p.paraphrases)]];
    default: return [];
  }
}

function bars(daily) {
  const max = Math.max(1, ...daily);
  return h("div", { class: "mv-spark", role: "img", "aria-label": t("memory.last_30", { n: num(sum(daily)) }) },
    ...daily.map((v) => h("i", { class: v ? "" : "is-zero", style: { height: Math.max(3, (v / max) * 100) + "%" } })));
}

function opened(s, goTo) {
  const rows = breakdown(s);
  return h("div", { class: "mv-store-more" },
    s.daily ? h("div", { class: "mv-more-chart" },
      h("p", { class: "hb-sectitle" }, t("memory.last_30", { n: num(sum(s.daily)) })), bars(s.daily)) : null,
    rows.length ? h("dl", { class: "mv-breakdown" }, ...rows.map(([k, v, f]) => h("div", { class: "mv-bd-row" },
      h("dt", {}, k), h("dd", {}, v),
      f != null ? h("span", { class: "mv-fill" }, h("i", { style: { width: Math.max(2, f * 100) + "%" } })) : null))) : null,
    s.key === "memories" ? h("button", { class: "hb-btn hb-btn--ghost hb-btn--sm", type: "button",
                                         onClick: (e) => { e.stopPropagation(); goTo("graph"); } }, t("memory.see_graph")) : null);
}

export function Overview({ goTo }) {
  let grid, sub, timer = null;
  const open = new Set();
  let last = null;

  function card(s) {
    const nt = note(s);
    const can = !!(s.daily || breakdown(s).length);
    const isOpen = can && open.has(s.key);
    const toggle = () => { if (open.has(s.key)) open.delete(s.key); else open.add(s.key); paint(); };
    return h("div", { class: "hb-card mv-store" + (isOpen ? " is-open" : ""), "data-store": s.key,
                      style: { "--mv-accent": `var(${ACCENT[s.key] || "--hb-accent"})` } },
      h(can ? "button" : "div", { class: "mv-store-face", type: can ? "button" : null,
                                  "aria-expanded": can ? String(isOpen) : null, onClick: can ? toggle : null },
        h("span", { class: "mv-store-head" }, h("span", { class: "mv-store-name" }, t(`memory.store_${s.key}`)),
          h("i", { class: "mv-store-dot" })),
        h("span", { class: "mv-store-total" }, total(s)),
        h("span", { class: "mv-store-detail" }, detail(s)),
        h("span", { class: "mv-store-note " + nt.cls }, nt.text)),
      isOpen ? opened(s, goTo) : null);
  }

  function paint() {
    if (!last) return;
    grid.replaceChildren(...(last.stores || []).map(card));
  }

  async function load() {
    const body = await api.memoryViewer("stats");
    if (!body) { sub.textContent = t("memory.load_error"); return; }
    last = body;
    const stores = body.stores || [];
    const size = stores.reduce((a, s) => a + (Number(s.bytes) || 0) + (s.key === "apps" ? Number(s.total) || 0 : 0), 0);
    sub.textContent = t("memory.ov_sub", { size: bytes(size), ago: ago(body.counted_at) });
    paint();
    clearTimeout(timer);
    if (stores.some((s) => s.pending)) timer = setTimeout(load, 2500);   // the app folders are still being measured
  }

  const el = h("div", { class: "mv-overview" },
    h("div", { class: "mv-ov-title" }, h("h2", {}, () => t("memory.ov_title")), h("p", { class: "mv-muted", ref: (x) => (sub = x) })),
    h("div", { class: "mv-stores", ref: (x) => (grid = x) }));

  let loaded = false;
  return { el, activate() { if (!loaded) { loaded = true; load(); } }, deactivate() {}, refresh() { if (loaded) load(); } };
}
