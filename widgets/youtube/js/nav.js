// youtube widget — THE BAR: the five tabs, then the platform icons and the plug, then the search (V2-885).
// Moved out of widget.js; selectTab is still the ONE transition between faces (V2-626).
//
// Operator, 2026-11-11: «la búsqueda también en la cabecera permanente… a la derecha del todo el botón de BUSCAR,
// y unos 30 px a su izquierda los dos iconos de conectores/plataformas». Three widths, never a ragged wrap: one line
// where it fits, the tools on a second aligned row when narrower, and on the phone a «⋯» menu for the secondary
// tabs — Inicio and the search always in sight. It is the HOUSE bar (V2-882, lib/toolbar.js), which MEASURES the
// step it needs instead of guessing from a breakpoint: lead = the tabs · tray = the secondary tabs (seen only in its
// ⋯ menu) + the platform icons and the plug · the search pinned right in its own column (style_cards.js).
import { Y } from "./state.js";
import { reportState } from "./report.js";
import { ICON_PLUG, ICON_SEARCH, svgEl, el, _TABS, tabLabel, applyTabClass, iconBtn, tt } from "./shared.js";
import { renderConn } from "./conn.js";
import { bar, fit } from "/frontend/app/lib/toolbar.js";

export function buildNav(root, ctx){
  const nav = el("div", "hb-yt-nav");
  const tabsBox = el("div", "hb-yt-tabs hb-bar-lead");
  tabsBox.setAttribute("role", "tablist");
  nav.appendChild(tabsBox);
  const tabBtns = {};
  const menu = el("div", "hb-yt-menu hb-bar-views");
  const selectTab = (tid) => {
    Y.tab = tid;
    Y.screen = null; Y.connErr = "";                       // choosing a tab is ONE transition (V2-626)
    applyTabClass(root);
    paintTabs();
    const cb = root.querySelector(".hb-yt-plug"); if(cb) cb.classList.remove("on");
    root.classList.remove("hb-yt-connmode");
    const connBox = root._hbYtEls && root._hbYtEls.conn; if(connBox) connBox.textContent = "";
    if(ctx && ctx.top) ctx.top();
    const bd = root._hbYtEls && root._hbYtEls.body; if(bd) bd.scrollTop = 0;
    reportState({view: tid});                              // V2-884 1a: the face he sees, the moment it changes
  };
  // The tabs' lit state has ONE painter: the chosen face wears .on, and while the connectors screen is open
  // no face is on screen, so none is lit. Every tab stays a way OUT (operator, 2026-10-26).
  const paintTabs = () => {
    Object.keys(tabBtns).forEach((k) => tabBtns[k].classList.toggle("on", !Y.screen && k === Y.tab));
    menu.querySelectorAll(".hb-yt-mitem").forEach((m) => m.classList.toggle("on", !Y.screen && m.dataset.tab === Y.tab));
  };
  _TABS.forEach((tid) => {
    const b = el("button", "hb-yt-tab" + (tid === Y.tab ? " on" : ""), tabLabel(tid));
    b.dataset.tab = tid;
    b.setAttribute("role", "tab");
    b.addEventListener("click", () => selectTab(tid));
    tabBtns[tid] = b;
    tabsBox.appendChild(b);
    if(tid === "inicio") return;                           // Inicio never hides, so it is never in the menu
    const m = el("button", "hb-yt-mitem", tabLabel(tid));
    m.dataset.tab = tid;
    m.addEventListener("click", () => selectTab(tid));
    menu.appendChild(m);
  });
  // RIGHT cluster: the platform icons and the plug, a --sp-6 gap, then the search pinned to the right edge.
  const tray = el("div", "hb-bar-tray");
  const right = el("div", "hb-yt-navright hb-bar-aux");
  const dots = el("div", "hb-yt-dots");
  right.appendChild(dots);
  const connBtn = el("button", "hb-yt-plug");
  connBtn.appendChild(svgEl(ICON_PLUG));
  connBtn.title = tt("sources_title", null, "Fuentes de vídeo / conectores");
  connBtn.setAttribute("aria-label", tt("connectors", null, "Conectores"));
  connBtn.addEventListener("click", () => {
    if(Y.screen){ selectTab(Y.tab); return; }              // toggle off → back to the active tab
    Y.screen = {view: "shelf"}; Y.connErr = "";
    connBtn.classList.add("on");
    paintTabs();
    renderConn(root._hbYtEls || {}, root, root._hbYtData || {}, ctx);
  });
  right.appendChild(connBtn);
  // The search is a DOOR, not a second field: it lands on Inicio with the one search box focused.
  const focusSearch = () => {
    if(Y.tab !== "inicio" || Y.screen) selectTab("inicio");
    const inp = root._hbYtEls && root._hbYtEls.sInp;
    if(inp){ inp.focus(); if(inp.select) inp.select(); }
  };
  const findBtn = iconBtn("hb-yt-find", ICON_SEARCH, tt("search_open", null, "Buscar vídeos"), focusSearch);
  tray.append(menu, right);
  nav.append(tray, findBtn);
  root.appendChild(bar(nav, {more: tt("more_tabs", null, "Más secciones")}));
  root._hbYtSelectTab = selectTab;
  root._hbYtTabBtns = tabBtns;
  root._hbYtPaintTabs = paintTabs;
  root._hbYtFocusSearch = focusSearch;
  return {dots, menu};
}

// Per render: every label re-read from the bundle (V2-694), the Cola tab and its menu row wear the count.
export function paintNav(root, data){
  if(!root._hbYtTabBtns) return;
  const nQ = Array.isArray(data.list) ? data.list.length : 0;
  const label = (k) => { const lab = tabLabel(k); return (k === "cola" && nQ) ? (lab + " · " + nQ) : lab; };
  Object.keys(root._hbYtTabBtns).forEach((k) => {
    root._hbYtTabBtns[k].textContent = label(k);
    if(k === "subs") root._hbYtTabBtns[k].dataset.short = tt("tab_subs_short", null, "Canales");   // the phone's row
  });
  root.querySelectorAll(".hb-yt-menu .hb-yt-mitem").forEach((m) => { m.textContent = label(m.dataset.tab); });
  if(root._hbYtPaintTabs) root._hbYtPaintTabs();
  fit(root.querySelector(".hb-yt-nav"));                  // a label that grew («Cola · 12») may need the next step
}
