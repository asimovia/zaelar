// ============================================================================
// memory/lists.js — the paged tabs of the memory viewer (V2-808): Facts · Conversation · Messages · Files · Apps ·
// System. Every one reads ONE page from the server (newest first, the server caps the size), shows it, and asks
// for the next page only when he presses «Load more». Search runs on the server; nothing is filtered here.
// ============================================================================
import { h } from "../../core/dom.js?v=2";
import * as api from "../../services/api.js?v=2";
import { t } from "../../core/i18n.js?v=1";
import { num, bytes, dateTime, date, label, memMeta } from "./format.js?v=1";

// A generic paged list. `opts.path` is the viewer endpoint, `opts.row(item)` paints one item, `opts.cursor(page)`
// turns a page's `next` into the params of the following call, `opts.filters` is an optional segmented control.
export function PagedList(opts) {
  let listEl, footEl, input, filterEl, loaded = false, seq = 0, timer = null, filter = opts.filters?.[0]?.value ?? "";
  let next = null;

  async function load(append) {
    const my = ++seq;
    const params = { limit: opts.rows, q: input ? input.value.trim() : "", ...(opts.filterParam ? { [opts.filterParam]: filter } : {}),
                     ...(append && next ? opts.cursor(next) : {}) };
    if (!append) { listEl.replaceChildren(); footEl.replaceChildren(h("span", { class: "mv-muted" }, t("memory.loading"))); }
    const page = await api.memoryViewer(opts.path, params);
    if (my !== seq) return;                                   // a newer search replaced this one
    if (!page) { footEl.replaceChildren(h("span", { class: "mv-muted" }, t("memory.load_error"))); return; }
    if (page.pending) {                                       // the server is still measuring (the app folders)
      footEl.replaceChildren(h("span", { class: "mv-muted" }, t("memory.store_apps_measuring")));
      setTimeout(() => { if (my === seq) load(false); }, 2500);
      return;
    }
    for (const it of page.items || []) listEl.append(opts.row(it));
    next = page.next;
    const empty = !listEl.children.length;
    // `replaceChildren(null)` paints the word «null»: a missing button is left out, never passed.
    footEl.replaceChildren(...[
      empty ? h("p", { class: "hb-empty-state" }, t("memory.list_empty")) : h("span", { class: "mv-muted" },
        page.more ? t("memory.list_shown", { n: num(listEl.children.length) }) : t("memory.list_end")),
      page.more ? h("button", { class: "hb-btn hb-btn--secondary hb-btn--sm", type: "button", onClick: () => load(true) },
                    t("memory.list_more")) : null].filter(Boolean));
  }

  const tools = opts.search !== false || opts.filters || opts.head;
  const el = h("div", { class: "mv-list-view" },
    !tools ? null : h("div", { class: "hb-toolbar hb-toolbar--sub mv-list-tools" },
      opts.search === false ? null : h("label", { class: "mv-search" },
        h("span", { class: "mv-sr" }, () => t("memory.search_label")),
        h("input", { class: "hb-input", type: "search", placeholder: () => t("memory.search_placeholder"),
                     ref: (x) => (input = x),
                     onInput: () => { clearTimeout(timer); timer = setTimeout(() => load(false), 300); } })),
      opts.filters ? h("div", { class: "mv-seg", role: "group", ref: (x) => (filterEl = x) },
        ...opts.filters.map((f) => h("button", { type: "button", "aria-pressed": String(f.value === filter),
          onClick: (e) => { filter = f.value; filterEl.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b === e.currentTarget))); load(false); } },
          () => t(f.key)))) : null,
      opts.head ? opts.head() : null),
    h(opts.grid ? "div" : "ul", { class: opts.grid ? "mv-grid" : "mv-rows", ref: (x) => (listEl = x) }),
    h("div", { class: "mv-list-foot", ref: (x) => (footEl = x) }));

  return {
    el,
    activate() { if (!loaded) { loaded = true; load(false); } },
    deactivate() {},
    // Live delta: only the head of an unfiltered list is refreshed, and only with rows it does not show yet.
    async refresh() {
      if (!loaded || !opts.prepend || (input && input.value.trim())) return;
      const page = await api.memoryViewer(opts.path, { limit: 20, ...(opts.filterParam ? { [opts.filterParam]: filter } : {}) });
      const top = Number(listEl.firstElementChild?.dataset.id || 0);
      const fresh = (page?.items || []).filter((it) => Number(it.id) > top).reverse();
      for (const it of fresh) listEl.prepend(opts.row(it));
    },
  };
}

const memRow = (m) => h("li", { class: "hb-card mv-row", "data-id": String(m.id) },
  h("p", { class: "mv-row-text" }, m.text), h("p", { class: "mv-row-meta" }, memMeta(m)));

export const FactsList = (rows) => PagedList({
  path: "facts", rows, prepend: true, row: memRow, filterParam: "layer", cursor: (n) => ({ before_id: n }),
  filters: [{ value: "all", key: "memory.facts_all" }, { value: "short", key: "memory.level_short_cap" },
            { value: "long", key: "memory.level_long_cap" }],
});

export const ConversationList = (rows) => PagedList({
  path: "conversation", rows, prepend: true, cursor: (n) => ({ before_id: n }),
  row: (m) => h("li", { class: "hb-card mv-row", "data-id": String(m.id) },
    h("p", { class: "mv-row-text" }, m.text), h("p", { class: "mv-row-meta" }, dateTime(m.created))),
});

export const MessagesList = (rows, platforms) => PagedList({
  path: "messages", rows, filterParam: "platform", cursor: (n) => ({ before_ts: n.ts, before_id: n.id }),
  filters: [{ value: "", key: "memory.facts_all" },
            ...platforms.map((p) => ({ value: p, key: "memory.platform_" + p }))],
  row: (m) => h("li", { class: "hb-card mv-row" },
    h("p", { class: "mv-row-text" }, m.body || label("memory.media_type_", m.media_type) || "—"),
    h("p", { class: "mv-row-meta" }, [label("memory.platform_", m.platform), m.chat_name || m.sender,
      t(m.direction === "out" ? "memory.msg_out" : "memory.msg_in"), dateTime(m.ts)].filter(Boolean).join(" · "))),
});

export const FilesList = () => PagedList({
  path: "files", rows: 60, search: false, grid: true, cursor: (n) => ({ offset: n }), filterParam: "kind",
  filters: [{ value: "", key: "memory.facts_all" }, { value: "img", key: "memory.files_photos" },
            { value: "vid", key: "memory.files_videos" }, { value: "aud", key: "memory.files_audio" },
            { value: "doc", key: "memory.files_documents" }],
  row: (f) => h("a", { class: "hb-card mv-file", href: `/widgets/mensajeria/asset/${encodeURIComponent(f.name)}`,
                       target: "_blank", rel: "noopener", title: () => t("memory.files_open") },
    f.thumb ? h("img", { src: `/api/memory/viewer/thumb/${encodeURIComponent(f.name)}`, alt: "", loading: "lazy",
                         decoding: "async" })
            : h("span", { class: "mv-file-kind" }, label("memory.media_kind_", f.kind) || t("memory.media_kind_doc")),
    h("span", { class: "mv-file-meta" }, `${bytes(f.bytes)} · ${date(f.mtime)}`)),
});

export const AppsList = () => {
  let max = 1;
  return PagedList({
    path: "apps", rows: 50, search: false, cursor: (n) => ({ offset: n }),
    row: (a) => {
      max = Math.max(max, a.bytes);
      const name = a.key === "results" ? t("memory.apps_results", { n: num(a.sheets || 0) })
        : (label("widgets.", a.key + ".name") || a.title || t("memory.app_unnamed"));
      return h("li", { class: "hb-card mv-row" },
        h("p", { class: "mv-row-text mv-row-strong" }, name),
        h("p", { class: "mv-row-meta" }, t("memory.apps_files", { n: num(a.files), size: bytes(a.bytes) }),
          a.mtime ? ` · ${date(a.mtime)}` : ""),
        h("div", { class: "mv-fill" }, h("i", { style: { width: Math.max(2, (a.bytes / max) * 100) + "%" } })));
    },
  });
};

export const SystemList = (rows, head) => PagedList({
  path: "system", rows, search: false, cursor: (n) => ({ before_id: n }), head,
  row: (e) => h("li", { class: "mv-row mv-row--flat" },
    h("span", { class: "mv-row-time" }, dateTime(e.ts)),
    h("span", { class: "mv-row-text" }, e.label)),
});
