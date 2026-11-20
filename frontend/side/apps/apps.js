// side/apps/apps.js — the side panel's widget catalogue, a component that imports only its folder and loads its own CSS.
// mount(host, bridge = { t, icon, load, open, scope, setScope, onChange }) → { show (re-reads), hide, unmount }. Drawn
// ONLY while shown: hidden, its bar would be a second `.cw-subtabs` beside the tasks tab's own.
import { scopeOf, SCOPES, tilesOf, widgetsOf } from "./model.js";

const el = (tag, cls, text, ...kids) => { const n = document.createElement(tag); if (cls) n.className = cls;
  if (text != null) n.textContent = text; n.append(...kids.filter(Boolean)); return n; };

export function mount(host, b) {
  const t = b.t || ((k) => k);
  if (!document.getElementById("side-apps-css")) document.head.append(Object.assign(el("link"),
    { id: "side-apps-css", rel: "stylesheet", href: new URL("./apps.css", import.meta.url).href }));
  let rows = [], shown = false, loads = 0;
  const tile = ({ w, customized, forkOf }) => {
    const thumb = el("span", "ap-thumb"); thumb.innerHTML = b.icon || "";
    if (customized) thumb.append(el("span", "ap-badge", t("chat.appsCustomBadge")));
    const btn = el("button", "ap-tile" + (customized ? " ap-customized" : ""), null, thumb,
                   el("span", "ap-name", w.name || w.id), forkOf && el("span", "ap-meta", t("chat.appsForkOf")));
    btn.dataset.app = w.id; btn.title = customized ? t("chat.appsCustomizedNote") : (w.name || w.id);
    btn.onclick = () => b.open(w.id); return btn;
  };
  const render = () => {
    if (!shown) return;
    const sc = scopeOf(b.scope()), tiles = tilesOf(rows, sc.id);
    const bar = el("div", "cw-subtabs", null, ...SCOPES.map((x) => Object.assign(
      el("button", "cw-subtab" + (x.id === sc.id ? " on" : ""), t(x.label)), { onclick: () => b.setScope(x.id) })));
    host.replaceChildren(bar, tiles.length ? el("div", "ap-grid", null, ...tiles.map(tile)) : el("div", "cw-empty", t(sc.empty)));
  };
  const refresh = async () => {
    const mine = ++loads; let got;
    try { got = await b.load(); } catch (_) { return; }                 // a failed read keeps what was shown
    if (mine === loads) { rows = widgetsOf(got); render(); }            // else a newer read is on its way
  };
  const off = b.onChange(render);
  return { show() { shown = true; render(); return refresh(); }, hide() { shown = false; host.replaceChildren(); },
           unmount() { shown = false; loads++; host.replaceChildren(); if (off) off(); } };
}
