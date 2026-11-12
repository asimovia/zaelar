// youtube widget — THE BAR: the five tabs, then the platform icons and the plug, then the search (V2-885).
// Moved out of widget.js; selectTab is still the ONE transition between faces (V2-626).
//
// Operator, 2026-11-11: «la búsqueda también en la cabecera permanente… a la derecha del todo el botón de BUSCAR,
// y unos 30 px a su izquierda los dos iconos de conectores/plataformas». Three widths, never a ragged wrap: one line
// where it fits, the tools on a second aligned row when narrower, and on the phone a «⋯» menu for the secondary
// tabs — Inicio and the search always in sight (the rules live in style_cards.js, keyed on the card's width).
import { Y } from "./state.js";
import { ICON_PLUG, ICON_SEARCH, ICON_MORE, svgEl, el, _TABS, tabLabel, applyTabClass, iconBtn, tt } from "./shared.js";
import { renderConn } from "./conn.js";

export function buildNav(root, ctx){
  const nav = el("div", "hb-yt-nav");
  const tabsBox = el("div", "hb-yt-tabs");
  tabsBox.setAttribute("role", "tablist");
  nav.appendChild(tabsBox);
  const tabBtns = {};
  const menu = el("div", "hb-yt-menu");
  menu.hidden = true;
  menu.setAttribute("role", "menu");
  const closeMenu = () => { menu.hidden = true; moreBtn.setAttribute("aria-expanded", "false"); };
  const selectTab = (tid) => {
    Y.tab = tid;
    Y.screen = null; Y.connErr = "";                       // choosing a tab is ONE transition (V2-626)
    applyTabClass(root);
    paintTabs();
    closeMenu();
    const cb = root.querySelector(".hb-yt-plug"); if(cb) cb.classList.remove("on");
    root.classList.remove("hb-yt-connmode");
    const connBox = root._hbYtEls && root._hbYtEls.conn; if(connBox) connBox.textContent = "";
    if(ctx && ctx.top) ctx.top();
    const bd = root._hbYtEls && root._hbYtEls.body; if(bd) bd.scrollTop = 0;
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
    m.setAttribute("role", "menuitem");
    m.addEventListener("click", () => selectTab(tid));
    menu.appendChild(m);
  });
  // RIGHT cluster: the platform icons and the plug, a --sp-6 gap, then the search pinned to the right edge.
  const right = el("div", "hb-yt-navright");
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
  right.appendChild(findBtn);
  const moreBtn = iconBtn("hb-yt-menubtn", ICON_MORE, tt("more_tabs", null, "Más secciones"), () => {
    menu.hidden = !menu.hidden;
    moreBtn.setAttribute("aria-expanded", menu.hidden ? "false" : "true");
  });
  moreBtn.setAttribute("aria-haspopup", "menu");
  moreBtn.setAttribute("aria-expanded", "false");
  right.appendChild(moreBtn);
  right.appendChild(menu);
  nav.addEventListener("focusout", (e) => { if(!nav.contains(e.relatedTarget)) closeMenu(); });
  nav.addEventListener("keydown", (e) => { if(e.key === "Escape") closeMenu(); });
  nav.appendChild(right);
  root.appendChild(nav);
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
}
