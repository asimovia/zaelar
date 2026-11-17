// youtube widget — THE ONE SEARCH DOOR (2026-11-17, the YouTube app's own): the bar's 🔍 turns the bar itself into the
// field — ← · field · ✕ — and an empty field lists his recent searches (`recent_queries`, written by the `search`
// action). The results page keeps the query in that field; ← leaves the typing, and over the results it drops them
// (`clear_search`) and goes back to the catalogue. Enter is the same `search` the voice sends. Built ONCE with the bar,
// so a repaint never eats what he is typing; only its value and the mode are painted per render.
import { Y } from "./state.js";
import { ICON_SEARCH, ICON_CLEAR, ICON_BACK, ICON_CLOCK, el, iconBtn, svgEl, tt } from "./shared.js";
import { fit } from "/frontend/app/lib/toolbar.js";

const norm = (s) => String(s || "").trim().toLowerCase();

export function buildSearch(root, ctx, selectTab){
  const form = el("form", "hb-yt-search");
  form.setAttribute("role", "search");
  const inp = el("input", "");
  inp.type = "search"; inp.name = "q"; inp.autocomplete = "off"; inp.enterKeyHint = "search";
  inp.placeholder = tt("search_ph", null, "Buscar en YouTube…");
  inp.setAttribute("aria-label", tt("search_label", null, "Buscar vídeos"));
  const back = iconBtn("hb-yt-sbtn hb-yt-sback", ICON_BACK, tt("search_back", null, "Volver"), () => {
    const d = root._hbYtData || {};
    const band = (d.search_results || []).length || d.adding;
    if(Y.searching && band) inp.value = String(d.adding || d.search_query || "");   // back to the results he typed over
    else {
      if(band && ctx && ctx.action) ctx.action("clear_search", {});                 // off the results: the catalogue
      inp.value = "";
    }
    Y.searching = false;
    inp.blur();
    paintSearchMode(root);
  });
  const clr = iconBtn("hb-yt-sbtn hb-yt-sclr", ICON_CLEAR, tt("clear_text", null, "Borrar el texto"), () => {
    inp.value = ""; Y.searching = true; inp.focus(); paintSearchMode(root);
  });
  const go = el("button", "hb-yt-sbtn go");
  go.type = "submit";
  go.appendChild(svgEl(ICON_SEARCH));
  go.title = tt("search_go", null, "Buscar");
  go.setAttribute("aria-label", go.title);
  form.append(back, inp, clr, go);
  const submit = (q) => {
    q = String(q || "").trim();
    if(!q || !ctx || !ctx.action) return;
    inp.value = q;
    if(Y.tab !== "inicio" || Y.screen) selectTab("inicio");
    Y.searching = false;
    inp.blur();
    paintSearchMode(root);
    ctx.action("search", {query: q});                   // the same data-op the voice uses; nothing plays
  };
  form.addEventListener("submit", (e) => { e.preventDefault(); submit(inp.value); });
  inp.addEventListener("focus", () => { if(!Y.searching){ Y.searching = true; paintSearchMode(root); } });
  inp.addEventListener("input", () => paintSearchMode(root));
  // His recent searches: a panel at the top of the body, shown while he types into an empty (or matching) field.
  const recent = el("div", "hb-yt-recent");
  recent.setAttribute("role", "listbox");
  recent.setAttribute("aria-label", tt("recent_searches", null, "Búsquedas recientes"));
  root._hbYtSearch = {form, inp, clr, recent, submit};
  return {form, inp, clr, recent};
}

// Per render and on every change of mode: which face the bar wears, the field's value, the recent rows.
export function paintSearchMode(root){
  const S = root._hbYtSearch;
  if(!S) return;
  const d = root._hbYtData || {};
  const band = !Y.screen && Y.tab === "inicio" && ((d.search_results || []).length > 0 || !!d.adding);
  const typing = !!Y.searching && !Y.screen;
  if(document.activeElement !== S.inp && !typing) S.inp.value = String(d.adding || d.search_query || "");
  const q = norm(S.inp.value);
  const recents = (Array.isArray(d.recent_queries) ? d.recent_queries : []).filter((r) => !q || norm(r).includes(q));
  root.classList.toggle("hb-yt-smode", band || typing);
  root.classList.toggle("hb-yt-typing", typing);
  const onBand = !!d.search_query && norm(S.inp.value) === norm(d.search_query);   // the field still says the results' query
  root.classList.toggle("hb-yt-recents", typing && recents.length > 0 && !onBand);
  S.clr.style.visibility = S.inp.value ? "" : "hidden";
  const sig = recents.join("\n");
  if(S.recent.dataset.sig !== sig){
    S.recent.dataset.sig = sig;
    S.recent.textContent = "";
    recents.forEach((r) => {
      const b = el("button", "hb-yt-rq");
      b.type = "button";
      b.setAttribute("role", "option");
      b.append(svgEl(ICON_CLOCK), el("span", "", r));
      b.addEventListener("click", () => S.submit(r));
      S.recent.appendChild(b);
    });
  }
  fit(root.querySelector(".hb-yt-nav"));
}
