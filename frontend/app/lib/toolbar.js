// The widget's ONE bar (V2-882): one line at the width its content needs, then two rows, then a menu.
//
// A bar is `.hb-bar` with its parts in ORDER OF IMPORTANCE — `.hb-bar-lead` (the primary control and the
// navigation), `.hb-bar-title`, and a `.hb-bar-tray` holding the view switcher (`.hb-bar-views`) and the least
// important group (`.hb-bar-aux`: account, providers, plug). components.css draws each STEP; this measures which
// one the bar needs. A breakpoint cannot know: «Semana» and «Week» are different widths, and a provider more is
// another 28px. So the bar is tried at each step in order and keeps the first one where nothing is cut:
//   0 one line · 1 compact faces (`.hb-wide` → `.hb-narrow`, labels → icons) · 2 the aux group on a second row
//   · 3 the tray folds into ONE ⋯ menu, the title on its own row. Under PHONE px a bar with a tray is a menu.
// Shared with every widget (widgets/client_files.py SHARED_CLIENT_MODULES): `import { bar } from "/frontend/app/lib/toolbar.js"`.
import { MORE_ICON } from "./icons.js";

export const PHONE = 480;
const PARTS = ".hb-bar-lead,.hb-bar-title,.hb-bar-views,.hb-bar-aux";

function cut(b){
  if(b.scrollWidth > b.clientWidth + 1) return true;
  return [...b.querySelectorAll(PARTS)].some(p => p.offsetParent !== null && p.scrollWidth > p.clientWidth + 1);
}

/** Set `data-step` on the bar to the first step at which nothing in it is cut. */
export function fit(b){
  if(!b || !b.isConnected || !b.clientWidth) return;
  const tray = !!b.querySelector(".hb-bar-tray > *"), aux = !!b.querySelector(".hb-bar-aux");
  const last = tray ? 3 : (aux ? 2 : 1);
  let s = (tray && b.clientWidth < PHONE) ? 3 : 0;
  for(; s < last; s++){ b.dataset.step = String(s); if(!cut(b)) break; }
  b.dataset.step = String(s);
  if(s < 3) b.classList.remove("is-open");
}

/** Make `b` a bar: add its ⋯ button (labelled `more`), fit it now and on every change of its width. */
export function bar(b, { more = "More" } = {}){
  b.classList.add("hb-bar");
  let m = b.querySelector(":scope > .hb-bar-more");
  if(!m && b.querySelector(".hb-bar-tray")){
    m = document.createElement("button"); m.type = "button";
    m.className = "hb-bar-more hb-iconbtn hb-iconbtn--framed"; m.innerHTML = MORE_ICON;
    m.setAttribute("aria-label", more); m.title = more; m.setAttribute("aria-expanded", "false");
    m.onclick = ev => { ev.stopPropagation(); m.setAttribute("aria-expanded", String(b.classList.toggle("is-open"))); };
    b.appendChild(m);
    // a choice made inside the menu closes it, as any menu does
    b.querySelector(".hb-bar-tray").addEventListener("click", () => { b.classList.remove("is-open"); m.setAttribute("aria-expanded", "false"); });
  }
  let w = -1;
  const ro = new ResizeObserver(() => {
    if(!b.isConnected){ ro.disconnect(); return; }
    if(b.clientWidth !== w){ w = b.clientWidth; fit(b); }
  });
  ro.observe(b);
  fit(b);
  return b;
}

/** Content tooltips that never leave their scroller: `[data-hb-tip]` under `sc` shows ONE `.hb-tipbox` drawn
 *  inside `sc` (which must be positioned), under the element and clamped to the scroller's width. */
export function tips(sc){
  const box = document.createElement("div"); box.className = "hb-tipbox"; box.hidden = true; box.setAttribute("aria-hidden", "true");
  sc.addEventListener("mouseover", e => {
    const t = e.target.closest && e.target.closest("[data-hb-tip]");
    if(!t || !sc.contains(t)){ box.hidden = true; return; }
    if(box.parentNode !== sc) sc.appendChild(box);
    box.textContent = t.dataset.hbTip; box.hidden = false;
    const r = t.getBoundingClientRect(), s = sc.getBoundingClientRect();
    const x = Math.min(r.left - s.left + sc.scrollLeft, sc.scrollLeft + sc.clientWidth - box.offsetWidth - 4);
    box.style.left = Math.max(sc.scrollLeft + 4, x) + "px"; box.style.top = (r.bottom - s.top + sc.scrollTop + 4) + "px";
  });
  sc.addEventListener("mouseleave", () => { box.hidden = true; });
  return sc;
}
