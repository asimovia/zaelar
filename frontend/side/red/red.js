// side/red/red.js — the Network column (V2-866 F3): pending consent cards, connected agents, what he shares with
// each (✕ = stop sharing) and recent activity, all over the one read the bridge keeps. Off (no answer): no body.
// It imports nothing from outside this folder.
//   mount(host, bridge) → { show(), hide(), unmount() }   ·   cardView(card, cls, bridge) → a consent card's node
//   bridge: { t(key, params), network() → the last answer, watch(fn) → off, refresh(), answer(id, yes) → ok, revoke(cid, item) }
import { isOn, blocks } from "./model.js";

const el = (tag, cls, ...kids) => { const e = document.createElement(tag); if (cls) e.className = cls; e.append(...kids.filter((k) => k != null)); return e; };
const btn = (cls, label, onClick, title) => { const b = el("button", cls, label); b.onclick = onClick; if (title) b.title = title; return b; };
// Its stylesheet sits beside it and is linked once, by the component itself: no shell lists it.
const linkCss = (href = new URL("./red.css", import.meta.url).href) => document.querySelector(`link[href="${href}"]`)
  || document.head.append(Object.assign(document.createElement("link"), { rel: "stylesheet", href }));

const answered = new Map();     // card id → "yes" | "no" | "error": one record for the chat's cards and the column's

/** A consent card: its question and two buttons, or — once answered — what he answered. The chat draws it too. */
export function cardView(c, cls, bridge) {
  const { t } = bridge, done = answered.get(c.id), p = c.type === "propose";
  const answer = async (yes) => {
    let ok = false; try { ok = !!(await bridge.answer(c.id, yes)); } catch (_) { /* told as failed */ }
    answered.set(c.id, ok ? (yes ? "yes" : "no") : "error"); r.replaceWith(cardView(c, cls, bridge));
  };
  const r = el("div", `${cls} a2a a2a-card`, el("div", "cl-q", t(p ? "a2a.card_propose" : "a2a.card_request", { name: c.name || "?" })),
    c.note ? el("div", "a2a-note", String(c.note)) : null,
    done ? el("div", "a2a-done", t(done === "error" ? "a2a.failed" : done === "yes" ? "a2a.answered_yes" : "a2a.answered_no"))
      : el("div", "cl-cbtns", btn("cl-b on", t(p ? "a2a.connect" : "a2a.accept"), () => answer(true)),
                             btn("cl-b", t(p ? "a2a.no" : "a2a.decline"), () => answer(false))));
  r.dataset.card = c.id || ""; return r;
}

export function mount(host, bridge) {
  const { t } = bridge;
  linkCss();
  const root = host.appendChild(el("div", "cl-list"));
  const sec = (key, rows) => el("div", "a2a-sec", el("div", "cn-fam", t(key)), ...(rows.length ? rows : [el("div", "cw-empty", t("a2a.none"))]));
  function render() {
    const net = bridge.network();
    if (!isOn(net)) return root.replaceChildren();
    const b = blocks(net);
    root.replaceChildren(sec("a2a.pending", b.pending.map((c) => cardView(c, "cl-row", bridge))),
      sec("a2a.relationships", b.relationships.map((r) => el("div", "cl-row a2a-rel", el("span", "a2a-name", r.name), el("span", "ctnote", r.peer)))),
      sec("a2a.grants", b.grants.map((g) => el("div", "cl-row a2a-share", el("span", "a2a-name", g.name), ...g.items.map((item) =>
        el("span", "a2a-chip", String(item), btn("cl-b", "✕", () => bridge.revoke(g.cid, item), t("a2a.stop_sharing"))))))),
      sec("a2a.recent", b.recent.map((e) => el("div", "cl-row a2a-ev", el("span", null, e.text), el("span", "ctnote", e.who)))));
  }
  const off = bridge.watch ? bridge.watch(render) : (render(), null);
  return { show: () => bridge.refresh(), hide() {}, unmount() { if (off) off(); root.remove(); } };
}
