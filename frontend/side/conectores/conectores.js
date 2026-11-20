// side/conectores/conectores.js — the Connectors column (V2-561/V2-526): what he CAN connect, by family, with its state;
// folded below, what we do not have yet («I want it»). It imports nothing from outside this folder.
//   mount(host, bridge) → { show(), hide(), unmount() }
//   bridge: { t(key, params), load() → { live, wish }, manage(id), want(entry), watch(fn) → off }
// `manage(id)` is the shell's door to the CREDENTIAL surface — this list never holds a form (V2-520).
import { byFamily, liveState } from "./model.js";

const el = (tag, cls, ...kids) => { const e = document.createElement(tag); if (cls) e.className = cls; e.append(...kids.filter((k) => k != null)); return e; };
const btn = (cls, label, onClick, off) => { const b = el("button", cls, label); b.onclick = onClick; b.disabled = !!off; return b; };
// Its stylesheet sits beside it and is linked once, by the component itself: no shell lists it.
const linkCss = (href = new URL("./conectores.css", import.meta.url).href) => document.querySelector(`link[href="${href}"]`)
  || document.head.append(Object.assign(document.createElement("link"), { rel: "stylesheet", href }));

export function mount(host, bridge) {
  const { t } = bridge;
  linkCss();
  const requested = new Set();                 // «I want it» once per id: the row says it was sent
  const root = host.appendChild(el("div", "cl-list"));
  let data = { live: [], wish: [] }, retry = null, gone = false;

  // A failed read (the engine still booting) used to be painted as «no connectors» and never retried. Retried while shown.
  async function load(tries = 6) {
    clearTimeout(retry);
    let got = null; try { got = await bridge.load(); } catch (_) { /* painted as empty, then retried */ }
    if (gone) return; data = { live: (got && got.live) || [], wish: (got && got.wish) || [] };
    render();
    if (!data.live.length && tries > 1) retry = setTimeout(() => load(tries - 1), 2000);
  }
  const want = (m) => { if (requested.has(m.id)) return; requested.add(m.id); render();
    try { Promise.resolve(bridge.want(m)).catch(() => {}); } catch (_) { /* best-effort: the row already shows it */ } };
  const row = (cls, name, on, meta, button, title) => { const r = el("div", "cl-row" + cls,
    el("div", "cl-main", el("div", "cl-name", el("span", "cl-dot" + (on ? " on" : "")), name), el("div", "cl-meta", meta)),
    el("div", "cl-btns", button)); if (title) r.title = title; return r; };
  const liveRow = (c) => { const s = liveState(c);
    return row("", c.label || c.id, s.on, c.services ? t("config.cx.of_services", { n: s.n, total: s.total })
      : t(c.connected ? "chat.connected" : "chat.disconnected"),
      btn("cl-b" + (s.on ? "" : " on"), t(s.on ? "chat.manageBtn" : "chat.connectBtn"), () => bridge.manage(c.id))); };
  const wishRow = (m) => { const imp = m.state === "not-possible", asked = requested.has(m.id);
    const why = imp ? ((k) => (t(k) !== k ? t(k) : m["why-not"] || ""))("connectors." + m.id + ".why_not") : "";  // the pack's key first
    return row(imp ? " cn-imposs" : "", m.label || m.id, false, t(imp ? "chat.connWishlistImpossible" : "chat.connWishlistPlanned"),
      imp ? null : btn("cl-b" + (asked ? "" : " on"), t(asked ? "chat.connWantedBtn" : "chat.connWantBtn"), () => want(m), asked), why); };
  // t() returns the KEY itself when a string is missing (truthy) — never `|| fam` here (V2-538).
  const fam = (f, tag = "div") => el(tag, "cn-fam", f === "google" ? "Google" : t("chat.connFamily." + f));

  function render() {
    const { live, wish } = data, open = !!(root.querySelector(".cn-soon") || {}).open, out = [];
    if (!live.length && !wish.length) out.push(el("div", "cw-empty", t("chat.connEmpty")));
    for (const [f, rows] of byFamily(live)) out.push(fam(f), ...rows.map(liveRow));
    if (wish.length) {
      const soon = el("details", "cn-soon", el("summary", "cn-fam", t("chat.connSoon", { n: wish.length })));
      for (const [f, rows] of byFamily(wish)) soon.append(fam(f), ...rows.map(wishRow));
      soon.open = open; out.push(soon);
    }
    root.replaceChildren(...out);
  }
  const off = bridge.watch ? bridge.watch(render) : (render(), null);
  return { show: () => load(), hide: () => clearTimeout(retry),
           unmount() { gone = true; clearTimeout(retry); if (off) off(); root.remove(); } };
}
