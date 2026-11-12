// youtube widget — the queue (Cola) and the saved lists (Listas) faces.
// Part of the client split out of widget.js (refactor2710-12 T-03); widget.js stays the entry with render().
//
// V2-885 — operator, 2026-11-11: «la Cola no es una lista de 200 filas: los elementos uno detrás de otro, bien
// separados y ordenados, la miniatura un poco más grande, el título, el canal debajo, algún dato del vídeo, botones
// claros para quitarlo o subirlo/bajarlo». And an empty section says so AND offers what to do: «Listas» offers a new
// list whose field comes prefilled with a name and today's date.
import { Y } from "./state.js";
import { ICON_UP, ICON_DOWN, ICON_CLEAR, ICON_PLAY, el, iconBtn, emptyState, tt } from "./shared.js";
import { hl } from "./channel.js";

function today(ctx){                                   // ctx.lang, the host's live language (a switch re-reads it)
  try{ return new Intl.DateTimeFormat(hl(ctx), {day: "numeric", month: "short", year: "numeric"}).format(new Date()); }
  catch(_){ return new Date().toISOString().slice(0, 10); }
}

export function buildQueueBoxes(root, ctx, body){
  const listBox = el("div", "hb-yt-list");
  body.appendChild(listBox);
  const subsBox = el("div", "hb-yt-subs");             // V2-632: followed authors, OUR references
  body.appendChild(subsBox);
  const listsBox = el("div", "hb-yt-mylists");         // V2-632: saved lists
  body.appendChild(listsBox);
  // The NEW LIST form is built ONCE, outside the rows rebuilt per render: a repaint must never eat the name he is
  // typing (the old save row was rebuilt on every SSE frame). Saving keeps the queue under that name.
  const newList = el("form", "hb-yt-newlist");
  newList.hidden = true;
  const nlInp = el("input", "hb-yt-addinp");
  nlInp.name = "list_name";
  nlInp.setAttribute("aria-label", tt("new_list_name_label", null, "Nombre de la lista"));
  const nlSave = el("button", "hb-btn hb-btn--sm hb-btn--primary", tt("save", null, "Guardar"));
  nlSave.type = "submit";
  const nlNote = el("div", "hb-yt-note hb-yt-nlnote", "");
  const nlRow = el("div", "hb-yt-nlrow");
  nlRow.append(nlInp, nlSave, iconBtn("hb-yt-qbtn", ICON_CLEAR, tt("cancel", null, "Cancelar"), () => {
    Y.newList = false; newList.hidden = true;
  }));
  newList.append(nlRow, nlNote);
  newList.addEventListener("submit", (e) => {
    e.preventDefault();
    const v = (nlInp.value || "").trim();
    const n = Array.isArray((root._hbYtData || {}).list) ? root._hbYtData.list.length : 0;
    if(!v || !n || !ctx || !ctx.action) return;          // an empty queue has nothing to keep: the note says so
    ctx.action("save_list", {name: v});
    Y.newList = false; newList.hidden = true;
  });
  body.appendChild(newList);
  const addRow = el("div", "hb-yt-addrow");
  const addInp = el("input", "hb-yt-addinp");
  addInp.placeholder = tt("add_ph", null, "Pega un enlace de YouTube o escribe un título…");
  const addBtn = el("button", "hb-yt-btn", tt("add", null, "＋ Añadir"));
  const doAdd = () => {
    const v = (addInp.value || "").trim();
    if(!v || !ctx || !ctx.action) return;
    addInp.value = "";
    ctx.action("add", {url: v});                       // the server tries link/id first, then searches by name
  };
  addBtn.addEventListener("click", doAdd);
  addInp.addEventListener("keydown", (e) => { if(e.key === "Enter") doAdd(); });
  addRow.appendChild(addInp); addRow.appendChild(addBtn);
  body.appendChild(addRow);
  root._hbYtOpenNewList = () => {
    Y.newList = true; newList.hidden = false;
    nlInp.value = tt("new_list_default", {date: today(ctx)}, "Lista del {date}");
    paintNewList(root._hbYtData || {}, nlNote, nlSave);
    nlInp.focus(); nlInp.select();
  };
  return {listBox, subsBox, listsBox, addInp, newList, nlNote, nlSave};
}

function paintNewList(data, note, save){
  const n = Array.isArray(data.list) ? data.list.length : 0;
  note.textContent = n ? tt("new_list_note", {n}, "Guarda los {n} vídeos de la cola con este nombre.")
                       : tt("new_list_empty", null, "La cola está vacía: añade vídeos y guárdala después.");
  save.disabled = !n;
}

export function paintQueue(root, E, data, ctx){
  if(!E.listBox) return;
  E.listBox.textContent = "";
  const lst = Array.isArray(data.list) ? data.list : [];
  const filt = String(data.list_filter || "").trim().toLowerCase();
  // V2-467 — the list NAME takes precedence over the generic label.
  const _nom = String(data.list_name || "").trim();
  const _rot = _nom || tt("list", null, "Lista");
  const head = el("div", "hb-yt-listh", lst.length ? (_rot + " · " + lst.length) : _rot);
  if(filt){
    const chip = el("span", "hb-yt-chip", tt("filter_chip", {q: filt}, "filtro: «{q}» ✕"));
    chip.title = tt("clear_filter", null, "Quitar el filtro");
    chip.addEventListener("click", () => { if(ctx && ctx.action) ctx.action("filter_list", {q: ""}); });
    head.appendChild(chip);
  }
  E.listBox.appendChild(head);
  if(data.adding) E.listBox.appendChild(el("div", "hb-yt-note", tt("searching_q", {q: data.adding}, "Buscando «{q}»…")));
  const act = (n, p) => { if(ctx && ctx.action) ctx.action(n, p); };
  const pos = Number(data.pos != null ? data.pos : -1);
  let shown = 0;
  lst.forEach((it, i) => {
    const hay = ((it.title || "") + " " + (it.channel || "")).toLowerCase();
    if(filt && hay.indexOf(filt) < 0) return;
    shown++;
    const n = String(i + 1);
    const row = el("div", "hb-yt-row hb-yt-qrow" + (i === pos ? " playing" : ""));
    row.appendChild(el("span", "hb-yt-rown", i === pos ? "▶" : n));
    const th = document.createElement("img");
    th.className = "hb-yt-rimg"; th.loading = "lazy"; th.alt = "";
    if(it.videoId) th.src = "https://i.ytimg.com/vi/" + encodeURIComponent(it.videoId) + "/mqdefault.jpg";
    row.appendChild(th);
    const info = el("div", "hb-yt-qinfo");
    info.appendChild(el("span", "hb-yt-rowt", it.title || it.url || "—"));
    // V2-791 — with WHEN it was published: «which of these is today's?» is read at a glance; its length when known
    const sub = [it.channel, it.published, it.duration].filter(Boolean).join(" · ");
    if(sub) info.appendChild(el("span", "hb-yt-rowc", sub));
    row.appendChild(info);
    const acts = el("div", "hb-yt-qacts");
    acts.appendChild(iconBtn("hb-yt-qbtn play", ICON_PLAY, tt("play_from_here", null, "Reproducir desde aquí"), () => {
      act("play_item", {item: n});
      if(root._hbYtSelectTab) root._hbYtSelectTab("player");
    }));
    // Reordering by hand is the voice's own `move` (1-based `to`); the ends are disabled, never hidden.
    const up = iconBtn("hb-yt-qbtn up", ICON_UP, tt("move_up", null, "Subir"), () => act("move", {item: n, to: String(i)}));
    up.disabled = i === 0;
    const down = iconBtn("hb-yt-qbtn down", ICON_DOWN, tt("move_down", null, "Bajar"), () => act("move", {item: n, to: String(i + 2)}));
    down.disabled = i === lst.length - 1;
    const x = iconBtn("hb-yt-qbtn hb-yt-rowx", ICON_CLEAR, tt("remove_from_list", null, "Quitar de la lista"), () => act("remove", {item: n}));
    acts.append(up, down, x);
    row.appendChild(acts);
    row.addEventListener("click", () => {
      act("play_item", {item: n});
      if(root._hbYtSelectTab) root._hbYtSelectTab("player");
    });
    E.listBox.appendChild(row);
  });
  if(lst.length && filt && !shown) E.listBox.appendChild(el("div", "hb-yt-note", tt("list_no_match", null, "Nada en la lista casa con el filtro.")));
  if(!lst.length && !data.adding){
    E.listBox.appendChild(emptyState(tt("queue_empty", null, "La cola está vacía."), [
      {id: "search", label: tt("search_something", null, "Buscar algo"),
       run: () => { if(root._hbYtFocusSearch) root._hbYtFocusSearch(); }},
      {id: "paste", label: tt("paste_link", null, "Pegar un enlace"), run: () => { if(E.addInp) E.addInp.focus(); }}]));
  }
}

export function paintSavedLists(root, E, data, ctx){
  if(!E.listsBox) return;
  E.listsBox.textContent = "";
  const saved = (Array.isArray(data.lists) ? data.lists : []).filter((L) => String(L && L.name || "").trim());
  const head = el("div", "hb-yt-listh", tt("saved_lists_n", {n: saved.length}, "Listas guardadas · {n}"));
  if(saved.length){
    const nb = el("button", "hb-btn hb-btn--sm hb-btn--secondary hb-yt-newbtn", tt("new_list", null, "＋ Nueva lista"));
    nb.type = "button";
    nb.addEventListener("click", () => { if(root._hbYtOpenNewList) root._hbYtOpenNewList(); });
    head.appendChild(nb);
  }
  E.listsBox.appendChild(head);
  if(!saved.length && !Y.newList){
    E.listsBox.appendChild(emptyState(tt("lists_none", null, "No hay listas."), [
      {id: "new", label: tt("new_list", null, "＋ Nueva lista"), run: () => { if(root._hbYtOpenNewList) root._hbYtOpenNewList(); }},
      {id: "search", label: tt("search_open", null, "Buscar vídeos"), run: () => { if(root._hbYtFocusSearch) root._hbYtFocusSearch(); }}]));
  }
  saved.forEach((L) => {
    const nom = String(L.name).trim();
    const items = Array.isArray(L.items) ? L.items : [];
    const row = el("div", "hb-yt-row hb-yt-qrow");
    const first = items.find((x) => x && x.videoId);
    const th = document.createElement("img");
    th.className = "hb-yt-rimg"; th.loading = "lazy"; th.alt = "";
    if(first) th.src = "https://i.ytimg.com/vi/" + encodeURIComponent(first.videoId) + "/mqdefault.jpg";
    row.appendChild(th);
    const info = el("div", "hb-yt-qinfo");
    info.appendChild(el("span", "hb-yt-rowt", nom));
    info.appendChild(el("span", "hb-yt-rowc", tt("n_videos", {n: items.length}, "{n} vídeos")));
    row.appendChild(info);
    const acts = el("div", "hb-yt-qacts");
    const open = el("span", "hb-yt-chip", tt("open_to_queue", null, "abrir → cola"));
    const doOpen = (e) => {
      if(e) e.stopPropagation();
      if(ctx && ctx.action) ctx.action("open_list", {name: nom});
      if(root._hbYtSelectTab) root._hbYtSelectTab("cola");
    };
    open.addEventListener("click", doOpen);
    acts.appendChild(open);
    acts.appendChild(iconBtn("hb-yt-qbtn hb-yt-rowx", ICON_CLEAR, tt("delete_list", null, "Borrar la lista guardada"),
      () => { if(ctx && ctx.action) ctx.action("delete_list", {name: nom}); }));
    row.appendChild(acts);
    row.addEventListener("click", doOpen);
    E.listsBox.appendChild(row);
  });
  if(E.newList){
    E.newList.hidden = !Y.newList;
    if(Y.newList) paintNewList(data, E.nlNote, E.nlSave);
  }
}
