// youtube widget — THE ⋮ SHEET (2026-11-17, the YouTube app's own): a row's actions behind one button, opened as a
// sheet at the foot of the CARD over a scrim inside it — never fixed to the page, never above z-index 5. One sheet per
// card; a choice, a tap on the scrim or Escape closes it.
import { el, svgEl, ICON_MORE, tt } from "./shared.js";

// `opts` = [{label, run, disabled?}]; `title` names the row the sheet acts on.
export function openSheet(root, title, opts){
  closeSheet(root);
  const scrim = el("div", "hb-yt-scrim");
  const sheet = el("div", "hb-yt-sheet");
  sheet.setAttribute("role", "menu");
  sheet.setAttribute("aria-label", title || tt("more_actions", null, "Más acciones"));
  if(title) sheet.appendChild(el("div", "hb-yt-sheett", title));
  opts.forEach((o) => {
    const b = el("button", "hb-yt-sheeti", o.label);
    b.type = "button";
    b.setAttribute("role", "menuitem");
    b.disabled = !!o.disabled;
    if(o.id) b.dataset.opt = o.id;
    b.addEventListener("click", (e) => { e.stopPropagation(); closeSheet(root); o.run(); });
    sheet.appendChild(b);
  });
  scrim.addEventListener("click", (e) => { e.stopPropagation(); closeSheet(root); });
  const esc = (e) => { if(e.key === "Escape") closeSheet(root); };
  document.addEventListener("keydown", esc);
  root.append(scrim, sheet);
  root._hbYtSheet = {scrim, sheet, esc};
  const first = sheet.querySelector(".hb-yt-sheeti:not(:disabled)");
  if(first) first.focus({preventScroll: true});
  return sheet;
}

export function closeSheet(root){
  const s = root && root._hbYtSheet;
  if(!s) return;
  document.removeEventListener("keydown", s.esc);
  s.scrim.remove(); s.sheet.remove();
  root._hbYtSheet = null;
}

// The ⋮ button a row carries: its click never reaches the row (which would play it).
export function moreBtn(cls, label, onOpen){
  const b = el("button", "hb-yt-more3 " + (cls || ""));
  b.type = "button";
  b.title = label; b.setAttribute("aria-label", label);
  b.setAttribute("aria-haspopup", "menu");
  b.appendChild(svgEl(ICON_MORE));                    // the shell's ⋯, stood upright by the sheet's CSS
  b.addEventListener("click", (e) => { e.stopPropagation(); onOpen(); });
  return b;
}
