// ============================================================================
// memory/graph-view.js — the «Graph» tab of the memory viewer (V2-808).
//
// What it draws comes AGGREGATED from the server (`/api/memory/viewer/graph`): the concepts of a time window with
// their counts, the concept↔concept weights, and as many memory dots as the device's node budget allows. Raw
// memories travel only for the concept he selects, one page at a time (`/api/memory/viewer/concept`).
//
// Drawing: ONE <canvas>, sized to its section in device pixels and re-fitted when the section resizes — the
// previous map was absolutely positioned DOM in a world scaled once at open time, which is how the concept maps
// ended up pushed into the bottom-right corner. Level of detail: memory dots are skipped while they would be
// sub-pixel, labels only appear for the biggest concepts or once a node is large enough on screen. The layout
// runs in a Worker (`force-worker.js`) and stops when it settles; the canvas repaints only while something moves.
// ============================================================================
import { h } from "../../core/dom.js?v=2";
import * as store from "../../core/store.js?v=2";
import * as api from "../../services/api.js?v=2";
import { t } from "../../core/i18n.js?v=1";
import { num, ago, memMeta } from "./format.js?v=1";

const PALETTE = ["--hb-accent", "--hb-accent2", "--hb-warn", "--hb-ok", "--hb-risk", "--hb-muted"];
const PERIODS = [{ days: 1, key: "memory.period_1" }, { days: 7, key: "memory.period_7" },
                 { days: 30, key: "memory.period_30" }, { days: 0, key: "memory.period_all" }];
const FIT_PAD = 28, FIT_FOOT = 44;

// The view transform that puts a bounding box in the MIDDLE of a W×H panel, scaled to fill it (never past 2×).
// Exported: the rendered test reads it, and its disarm replaces it.
// `foot` is the band the legend covers at the bottom: the drawing is centred in what is left above it.
export function fitTransform(box, W, H, pad = FIT_PAD, foot = FIT_FOOT) {
  const bw = Math.max(1, box.x1 - box.x0), bh = Math.max(1, box.y1 - box.y0);
  const k = Math.min(2, Math.max(0.05, Math.min((W - 2 * pad) / bw, (H - 2 * pad - foot) / bh)));
  H -= foot;
  return { k, tx: W / 2 - ((box.x0 + box.x1) / 2) * k, ty: H / 2 - ((box.y0 + box.y1) / 2) * k };
}

const cap = (s) => (s ? s.charAt(0).toLocaleUpperCase(store.lang() || "en") + s.slice(1) : "");

export function GraphView({ tier }) {
  const st = {
    days: 30, layers: new Set(["short", "long"]), messages: false, data: null,
    nodes: [], drawLinks: [], pos: null, view: { k: 1, tx: 0, ty: 0 }, autoFit: true,
    selected: "", hover: -1, page: null, timeline: [], brushFrom: -1, settled: true, pulses: new Map(),
  };
  let canvas, section, aside, footer, showingEl, chipsEl, periodEl, bars, brushBox, worker, raf = 0, colors = [];
  let active = false;

  // ── data ──────────────────────────────────────────────────────────────────────────────────────────────
  const params = () => ({ days: st.days, layers: [...st.layers].join(","),
                          lanes: st.messages ? "own,messages" : "own", budget: tier.nodes });

  async function load(warm = false) {
    const data = await api.memoryViewer("graph", params());
    if (!data) { section.dataset.state = "error"; paintEmpty(t("memory.load_error")); return; }
    const prev = new Map();
    if (warm && st.pos) st.nodes.forEach((n, i) => prev.set(n.id, [st.pos[2 * i], st.pos[2 * i + 1]]));
    st.data = data;
    build(prev);
    renderChrome();
    if (st.selected && !data.concepts.some((c) => c.key === st.selected)) select("");
    else if (!st.selected && data.concepts.length) select(data.concepts[0].key);
  }

  function build(prev) {
    const d = st.data;
    const maxC = Math.max(1, ...d.concepts.map((c) => c.count));
    const idx = new Map();
    const nodes = [];
    d.concepts.forEach((c, i) => {
      idx.set(c.key, nodes.length);
      nodes.push({ id: "c:" + c.key, hub: true, key: c.key, label: cap(c.label), count: c.count, rank: i,
                   r: 9 + 17 * Math.sqrt(c.count / maxC), color: i % PALETTE.length });
    });
    const links = [], drawLinks = [];
    const maxW = Math.max(1, ...d.links.map((l) => l.w));
    for (const l of d.links) {
      const s = idx.get(l.a), e = idx.get(l.b);
      if (s == null || e == null) continue;
      links.push({ s, t: e, len: 190 - Math.min(80, l.w * 8), k: 0.015 + 0.04 * (l.w / maxW) });
      drawLinks.push({ s, t: e, w: 0.8 + 2.6 * Math.sqrt(l.w / maxW), hub: true });
    }
    for (const m of d.memories) {
      const home = idx.get(m.c[0]);
      if (home == null) continue;
      const i = nodes.length;
      nodes.push({ id: "m:" + m.id, mid: m.id, hub: false, key: m.c[0], r: 2.6 + 3 * Math.min(1, m.w || 0),
                   color: nodes[home].color, level: m.level });
      links.push({ s: home, t: i, len: nodes[home].r + 26, k: 0.12 });
      drawLinks.push({ s: home, t: i, w: 0.6, hub: false });
      for (const c of m.c.slice(1)) {
        const o = idx.get(c);
        if (o != null) links.push({ s: o, t: i, len: 140, k: 0.004 });
      }
    }
    st.nodes = nodes; st.drawLinks = drawLinks;
    st.pos = new Float32Array(nodes.length * 2);
    const seeds = nodes.map((n) => { const p = prev.get(n.id); return { r: n.r, hub: n.hub, x: p?.[0], y: p?.[1] }; });
    nodes.forEach((n, i) => { const p = prev.get(n.id); if (p) { st.pos[2 * i] = p[0]; st.pos[2 * i + 1] = p[1]; } });
    section.dataset.nodes = String(nodes.length);
    if (!nodes.length) { stopWorker(); paintEmpty(t("memory.graph_empty")); return; }
    section.dataset.state = "running";
    st.settled = false;
    startWorker({ nodes: seeds, links });
  }

  function startWorker(payload) {
    if (!worker) {
      worker = new Worker(new URL("./force-worker.js", import.meta.url));
      worker.onmessage = (ev) => {
        const m = ev.data || {};
        if (!m.pos || m.pos.length !== st.nodes.length * 2) return;   // a reply to a graph we replaced
        st.pos = m.pos;
        if (m.type === "settled") { st.settled = true; section.dataset.state = "settled"; }
        if (st.autoFit) fit();
        schedule();
      };
    }
    worker.postMessage(payload);
  }
  function stopWorker() { if (worker) { worker.terminate(); worker = null; } }

  // ── view ──────────────────────────────────────────────────────────────────────────────────────────────
  function bbox() {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    st.nodes.forEach((n, i) => {
      const x = st.pos[2 * i], y = st.pos[2 * i + 1], r = n.r + (n.hub ? 22 : 0);
      x0 = Math.min(x0, x - r); y0 = Math.min(y0, y - r); x1 = Math.max(x1, x + r); y1 = Math.max(y1, y + r);
    });
    return { x0, y0, x1, y1 };
  }
  function fit() {
    if (!st.nodes.length || !canvas) return;
    const W = canvas.clientWidth, H = canvas.clientHeight;
    if (W < 10 || H < 10) return;
    st.view = fitTransform(bbox(), W, H);
  }
  function resize() {
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const W = section.clientWidth, H = section.clientHeight;
    canvas.width = Math.max(1, Math.round(W * dpr)); canvas.height = Math.max(1, Math.round(H * dpr));
    canvas.style.width = W + "px"; canvas.style.height = H + "px";
    if (st.autoFit) fit();
    schedule();
  }
  function schedule() { if (!raf) raf = requestAnimationFrame(() => { raf = 0; draw(); }); }

  function readColors() {
    const cs = getComputedStyle(section);
    colors = PALETTE.map((v) => cs.getPropertyValue(v).trim() || "#999");
    return { bg: cs.getPropertyValue("--canvas").trim() || "#16191E", ink: cs.getPropertyValue("--hb-ink").trim() || "#eee" };
  }

  function draw() {
    if (!canvas || !st.pos) return;
    const c = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const { bg, ink } = readColors();
    const font = getComputedStyle(section).fontFamily;
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, canvas.width, canvas.height);
    const { k, tx, ty } = st.view;
    c.setTransform(dpr * k, 0, 0, dpr * k, dpr * tx, dpr * ty);
    const P = st.pos, N = st.nodes;
    const now = performance.now();
    // edges (under everything)
    for (const l of st.drawLinks) {
      const a = N[l.s], b = N[l.t];
      const ax = P[2 * l.s], ay = P[2 * l.s + 1], bx = P[2 * l.t], by = P[2 * l.t + 1];
      const sel = st.selected && (a.key === st.selected || (l.hub && b.key === st.selected));
      c.strokeStyle = colors[a.color];
      c.globalAlpha = l.hub ? (sel ? 0.85 : 0.42) : 0.22;
      c.lineWidth = (l.hub ? l.w * (sel ? 1.5 : 1) : l.w) / Math.max(0.6, k);
      c.beginPath();
      c.moveTo(ax, ay);
      if (l.hub) {                                 // a gentle curve: the bend is perpendicular to the chord
        const mx = (ax + bx) / 2, my = (ay + by) / 2, dx = bx - ax, dy = by - ay;
        c.quadraticCurveTo(mx - dy * 0.12, my + dx * 0.12, bx, by);
      } else c.lineTo(bx, by);
      c.stroke();
    }
    c.globalAlpha = 1;
    // memory dots — level of detail: below ~1.5 px on screen a dot is a one-pixel square, not an arc
    const px = 1.5 / k;
    for (let i = 0; i < N.length; i++) {
      const n = N[i];
      if (n.hub) continue;
      c.fillStyle = colors[n.color];
      c.globalAlpha = n.level === "short" ? 0.95 : 0.7;
      if (n.r < px) c.fillRect(P[2 * i] - px / 2, P[2 * i + 1] - px / 2, px, px);
      else { c.beginPath(); c.arc(P[2 * i], P[2 * i + 1], n.r, 0, Math.PI * 2); c.fill(); }
      const p = st.pulses.get(n.mid);
      if (p && p > now) {
        c.globalAlpha = 0.9; c.strokeStyle = ink; c.lineWidth = 1.5 / k;
        c.beginPath(); c.arc(P[2 * i], P[2 * i + 1], n.r + 4 / k, 0, Math.PI * 2); c.stroke();
      }
    }
    c.globalAlpha = 1;
    // concepts
    for (let i = 0; i < N.length; i++) {
      const n = N[i];
      if (!n.hub) continue;
      const x = P[2 * i], y = P[2 * i + 1], col = colors[n.color];
      const sel = n.key === st.selected;
      const g = c.createRadialGradient(x, y, n.r * 0.6, x, y, n.r * (sel ? 3.6 : 2.6));
      g.addColorStop(0, col); g.addColorStop(1, "transparent");
      c.globalAlpha = sel ? 0.42 : 0.18;
      c.fillStyle = g; c.beginPath(); c.arc(x, y, n.r * (sel ? 3.6 : 2.6), 0, Math.PI * 2); c.fill();
      c.globalAlpha = 1;
      if (sel) {
        c.strokeStyle = col; c.globalAlpha = 0.75; c.lineWidth = 2 / k;
        c.beginPath(); c.arc(x, y, n.r + 6 / k, 0, Math.PI * 2); c.stroke(); c.globalAlpha = 1;
      }
      c.fillStyle = col; c.strokeStyle = bg; c.lineWidth = 3 / k;
      c.beginPath(); c.arc(x, y, n.r, 0, Math.PI * 2); c.fill(); c.stroke();
      // labels — level of detail: the biggest few always, the rest once they are big enough on screen
      if (n.rank < 10 || n.r * k >= 12 || sel || i === st.hover) {
        c.fillStyle = ink;
        c.font = `${sel ? 700 : 600} ${13 / k}px ${font}`;
        c.textAlign = "center"; c.textBaseline = "top";
        const text = `${n.label} · ${num(n.count)}`;
        c.strokeStyle = bg; c.lineWidth = 4 / k; c.lineJoin = "round";   // a halo: legible over the dots
        c.strokeText(text, x, y + n.r + 6 / k);
        c.fillText(text, x, y + n.r + 6 / k);
      }
    }
    if ([...st.pulses.values()].some((u) => u > now)) schedule();
  }

  function paintEmpty(msg) {
    if (!canvas) return;
    st.nodes = []; st.pos = new Float32Array(0); st.drawLinks = [];
    const c = canvas.getContext("2d");
    c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, canvas.width, canvas.height);
    emptyEl.textContent = msg; emptyEl.hidden = false;
    renderChrome();
  }

  // ── interaction ───────────────────────────────────────────────────────────────────────────────────────
  function at(ev) {
    const r = canvas.getBoundingClientRect();
    const { k, tx, ty } = st.view;
    const wx = (ev.clientX - r.left - tx) / k, wy = (ev.clientY - r.top - ty) / k;
    let best = -1, bd = Infinity;
    st.nodes.forEach((n, i) => {
      const dx = st.pos[2 * i] - wx, dy = st.pos[2 * i + 1] - wy, d = Math.sqrt(dx * dx + dy * dy);
      const reach = n.r + 6 / k;
      if (d <= reach && (d < bd || (n.hub && best >= 0 && !st.nodes[best].hub))) { best = i; bd = d; }
    });
    return best;
  }
  function onWheel(e) {
    e.preventDefault();
    zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - canvas.getBoundingClientRect().left,
           e.clientY - canvas.getBoundingClientRect().top);
  }
  function zoomAt(f, lx, ly) {
    const v = st.view, nk = Math.max(0.05, Math.min(8, v.k * f));
    const wx = (lx - v.tx) / v.k, wy = (ly - v.ty) / v.k;
    st.view = { k: nk, tx: lx - wx * nk, ty: ly - wy * nk };
    st.autoFit = false; schedule();
  }
  function onDown(e) {
    if (e.button !== 0) return;
    const sx = e.clientX, sy = e.clientY, v0 = { ...st.view };
    let moved = false;
    const move = (ev) => {
      if (Math.abs(ev.clientX - sx) + Math.abs(ev.clientY - sy) > 3) moved = true;
      if (!moved) return;
      st.view = { k: v0.k, tx: v0.tx + ev.clientX - sx, ty: v0.ty + ev.clientY - sy };
      st.autoFit = false; schedule();
    };
    const up = (ev) => {
      window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up);
      if (!moved) { const i = at(ev); if (i >= 0) select(st.nodes[i].key); }
    };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  }
  function onMove(e) {
    const i = at(e);
    if (i !== st.hover) { st.hover = i; canvas.style.cursor = i >= 0 ? "pointer" : "grab"; schedule(); }
  }

  // ── the detail panel ──────────────────────────────────────────────────────────────────────────────────
  let detailHead, detailList, detailFoot;
  async function select(key) {
    st.selected = key; schedule();
    detailList.replaceChildren(); detailFoot.replaceChildren();
    if (!key) { detailHead.replaceChildren(h("p", { class: "mv-muted" }, t("memory.detail_empty"))); return; }
    await page(key, 0);
  }
  async function page(key, before) {
    const p = await api.memoryViewer("concept", { key, ...params(), before_id: before || "", limit: tier.rows > 50 ? 20 : 10 });
    if (!p || key !== st.selected) return;
    if (!before) {
      const c = (st.data?.concepts || []).find((x) => x.key === key);
      const color = `var(${PALETTE[(c ? st.data.concepts.indexOf(c) : 0) % PALETTE.length]})`;
      detailHead.replaceChildren(
        h("p", { class: "hb-sectitle" }, t("memory.detail_kicker")),
        h("h2", { class: "mv-detail-title", style: { color } }, cap(p.label)),
        h("p", { class: "mv-muted" }, t("memory.detail_line", { count: num(p.count), short: num(p.short), ago: ago(p.last) })),
        h("div", { class: "mv-chips" }, ...p.related.map((r) => h("button", {
          class: "hb-badge hb-badge--bare mv-chip", type: "button", onClick: () => select(r.key) },
          `${cap(r.key)} · ${num(r.count)}`))),
      );
      st.page = { items: [], count: p.count };
    }
    st.page.items.push(...p.items);
    for (const m of p.items) {
      detailList.append(h("li", { class: "hb-card mv-pill" },
        h("p", { class: "mv-pill-text" }, m.text), h("p", { class: "mv-pill-meta" }, memMeta(m))));
    }
    detailFoot.replaceChildren(...[h("span", {}, t("memory.page_of", { shown: num(st.page.items.length), total: num(p.count) })),
      p.more ? h("button", { class: "hb-btn hb-btn--ghost hb-btn--sm", type: "button",
                             onClick: () => page(key, p.next) }, t("memory.load_more")) : null].filter(Boolean));
  }

  // ── chrome: filters, counters, the time brush ─────────────────────────────────────────────────────────
  let emptyEl;
  function renderChrome() {
    const d = st.data;
    periodEl.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed",
      String(st.brushFrom < 0 && Number(b.dataset.days) === st.days)));
    const lc = d?.layer_counts || { short: 0, long: 0, messages: 0 };
    chipsEl.replaceChildren(
      chip("short", t("memory.layer_short", { n: num(lc.short) }), st.layers.has("short"), () => toggleLayer("short")),
      chip("long", t("memory.layer_long", { n: num(lc.long) }), st.layers.has("long"), () => toggleLayer("long")),
      chip("messages", t("memory.lane_messages", { n: num(lc.messages) }), st.messages, () => { st.messages = !st.messages; load(); }),
    );
    showingEl.textContent = d ? t("memory.showing", { shown: num(d.shown.nodes), total: num(d.total.nodes), cap: num(tier.nodes) }) : "";
    if (emptyEl && st.nodes.length) emptyEl.hidden = true;
  }
  const chip = (kind, text, on, fn) => h("button", { class: `mv-layer mv-layer--${kind}`, type: "button",
                                                    "aria-pressed": String(on), onClick: fn }, text);
  function toggleLayer(l) {
    if (st.layers.has(l) && st.layers.size === 1) return;   // one layer always stays on
    st.layers.has(l) ? st.layers.delete(l) : st.layers.add(l);
    load();
  }
  function setPeriod(days) { st.days = days; st.brushFrom = -1; st.autoFit = true; load(); loadTimeline(); }

  async function loadTimeline() {
    const span = st.days === 0 ? 90 : Math.max(14, st.days);
    const tl = await api.memoryViewer("timeline", { days: span });
    const byDay = new Map((tl?.days || []).map((r) => [r.day, r.own]));
    const out = [];
    for (let i = span - 1; i >= 0; i--) {
      const d = new Date(Date.now() - i * 86400000);
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      out.push({ day: key, n: byDay.get(key) || 0 });
    }
    st.timeline = out;
    paintBrush();
  }
  function paintBrush() {
    const max = Math.max(1, ...st.timeline.map((b) => b.n));
    const span = st.timeline.length;
    const from = st.brushFrom >= 0 ? st.brushFrom : (st.days ? Math.max(0, span - st.days) : 0);
    bars.replaceChildren(...st.timeline.map((b, i) => h("div", {
      class: "mv-bar" + (i >= from ? " is-in" : ""), style: { height: Math.max(3, (b.n / max) * 100) + "%" },
      title: `${b.day} · ${num(b.n)}` })));
    brushBox.style.left = (from / Math.max(1, span)) * 100 + "%";
    footer.querySelector(".mv-brush-range").textContent =
      st.timeline.length ? `${st.timeline[from]?.day || ""} — ${st.timeline[span - 1].day}` : "";
  }
  function brushDown(e) {
    const r = bars.getBoundingClientRect();
    const idx = (x) => Math.max(0, Math.min(st.timeline.length - 1, Math.floor(((x - r.left) / r.width) * st.timeline.length)));
    const move = (ev) => { st.brushFrom = idx(ev.clientX); paintBrush(); };
    const up = () => {
      window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up);
      st.days = st.timeline.length - st.brushFrom; st.autoFit = true; load();
    };
    move(e);
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  }

  // ── DOM ───────────────────────────────────────────────────────────────────────────────────────────────
  const zoomBtn = (key, glyph, fn) => h("button", { class: "hb-iconbtn hb-iconbtn--framed hb-iconbtn--lg", type: "button",
                                                    "aria-label": () => t(key), title: () => t(key), onClick: fn }, glyph);
  const el = h("div", { class: "mv-graph" },
    h("div", { class: "hb-toolbar hb-toolbar--sub mv-filters" },
      h("div", { class: "mv-seg", role: "group", "aria-label": () => t("memory.period_label"), ref: (x) => (periodEl = x) },
        ...PERIODS.map((p) => h("button", { type: "button", "data-days": String(p.days), "aria-pressed": "false",
                                            onClick: () => setPeriod(p.days) }, () => t(p.key)))),
      h("div", { class: "mv-layers", role: "group", "aria-label": () => t("memory.layers_label"), ref: (x) => (chipsEl = x) }),
      h("span", { class: "hb-toolbar-spacer" }),
      h("p", { class: "mv-showing", ref: (x) => (showingEl = x) }),
    ),
    h("div", { class: "mv-graph-body" },
      h("section", { class: "mv-canvas-wrap", "aria-label": () => t("memory.graph_label"), ref: (x) => (section = x) },
        h("canvas", { class: "mv-canvas", ref: (x) => (canvas = x), onWheel, onPointerdown: onDown, onPointermove: onMove,
                      role: "img", "aria-label": () => t("memory.graph_label") }),
        h("p", { class: "hb-empty-state mv-graph-empty", hidden: true, ref: (x) => (emptyEl = x) }),
        h("div", { class: "mv-legend" },
          h("span", {}, h("i", { class: "mv-dot mv-dot--hub" }), () => t("memory.legend_concept")),
          h("span", {}, h("i", { class: "mv-dot" }), () => t("memory.legend_memory")),
          h("span", { class: "mv-legend-long" }, () => t("memory.legend_size")),
          h("span", { class: "mv-legend-long" }, () => t("memory.legend_width"))),
        h("div", { class: "mv-zoom" },
          zoomBtn("memory.zoom_in", "+", () => zoomAt(1.25, canvas.clientWidth / 2, canvas.clientHeight / 2)),
          zoomBtn("memory.zoom_out", "−", () => zoomAt(0.8, canvas.clientWidth / 2, canvas.clientHeight / 2)),
          zoomBtn("memory.fit", "⤢", () => { st.autoFit = true; fit(); schedule(); })),
      ),
      h("aside", { class: "mv-detail", "aria-label": () => t("memory.detail_label"), ref: (x) => (aside = x) },
        h("div", { class: "mv-detail-head", ref: (x) => (detailHead = x) }),
        h("ul", { class: "mv-detail-list", ref: (x) => (detailList = x) }),
        h("div", { class: "mv-detail-foot", ref: (x) => (detailFoot = x) })),
    ),
    h("footer", { class: "mv-brush", ref: (x) => (footer = x) },
      h("div", { class: "mv-brush-head" }, h("span", {}, () => t("memory.brush_label")), h("span", { class: "mv-brush-range" })),
      h("div", { class: "mv-brush-track", onPointerdown: brushDown },
        h("div", { class: "mv-bars", ref: (x) => (bars = x) }),
        h("div", { class: "mv-brush-box", ref: (x) => (brushBox = x) }))),
  );
  void aside;

  // The SECTION is observed, not the tab: the panel beside it (or under it, on a phone) changes the section's size
  // without the tab changing its own — measured at 375px, where the canvas kept a stale height.
  const ro = new ResizeObserver(() => { if (active) resize(); });
  ro.observe(section);

  return {
    el,
    activate() {
      active = true;
      resize();
      if (!st.data) { load(); loadTimeline(); } else schedule();
    },
    deactivate() { active = false; },
    refresh() { if (active) load(true); },
    pulse(ids) {
      const until = performance.now() + 4000;
      for (const id of ids || []) st.pulses.set(Number(id), until);
      if (active) schedule();
    },
    close() { stopWorker(); },
  };
}
