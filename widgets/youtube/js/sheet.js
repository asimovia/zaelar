// youtube widget — THE ⋮ SHEET (2026-11-17, the YouTube app's own): a row's actions behind one button, opened as a
// sheet at the foot of the CARD over a scrim inside it — never fixed to the page, never above z-index 5. One sheet per
// card; a choice, a tap on the scrim or Escape closes it and gives the focus back to the ⋮ that opened it. Escape is
// heard on the card itself, never on the document, so a card that goes away leaves no listener behind.
import { el, svgEl, ICON_MORE, tt } from "./shared.js";

// `opts` = [{label, run, disabled?}]; `title` names the row the sheet acts on; `opener` gets the focus back.
export function openSheet(root, title, opts, opener){
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
    b.addEventListener("click", (e) => { e.stopPropagation(); closeSheet(root, true); o.run(); });
    sheet.appendChild(b);
  });
  scrim.addEventListener("click", (e) => { e.stopPropagation(); closeSheet(root, true); });
  const esc = (e) => { if(e.key === "Escape"){ e.stopPropagation(); closeSheet(root, true); } };
  root.addEventListener("keydown", esc);
  root.append(scrim, sheet);
  // the ⋮ by its place too: a repaint over the same rows rebuilds them, and the focus belongs to that row's new ⋮
  const at = opener ? [...root.querySelectorAll(".hb-yt-more3")].indexOf(opener) : -1;
  root._hbYtSheet = {scrim, sheet, esc, opener, at};
  const first = sheet.querySelector(".hb-yt-sheeti:not(:disabled)");
  if(first) first.focus({preventScroll: true});
  return sheet;
}

// `back` = he closed it (a choice, the scrim, Escape): the focus returns to the ⋮, if that row is still there.
export function closeSheet(root, back){
  const s = root && root._hbYtSheet;
  if(!s) return;
  root.removeEventListener("keydown", s.esc);
  s.scrim.remove(); s.sheet.remove();
  root._hbYtSheet = null;
  const to = s.opener && s.opener.isConnected ? s.opener : (s.at >= 0 ? root.querySelectorAll(".hb-yt-more3")[s.at] : null);
  if(back && to) to.focus({preventScroll: true});
}

// The ⋮ button a row carries: its click never reaches the row (which would play it).
export function moreBtn(cls, label, onOpen){
  const b = el("button", "hb-yt-more3 " + (cls || ""));
  b.type = "button";
  b.title = label; b.setAttribute("aria-label", label);
  b.setAttribute("aria-haspopup", "menu");
  b.appendChild(svgEl(ICON_MORE));                    // the shell's ⋯, stood upright by the sheet's CSS
  b.addEventListener("click", (e) => { e.stopPropagation(); onOpen(b); });
  return b;
}
