// youtube widget — the Inicio face: the search box on top, then EITHER the results OR the catalogue (V2-885).
//
// Operator, 2026-11-11: «si estoy buscando, lo PRIMERO que se ve son los resultados… sin búsqueda, una pantalla de
// introducción como un catálogo de Netflix — lo visto hace poco, mis canales favoritos… En ningún caso tiene sentido
// buscar y que la línea siguiente sea un recuadro diciéndome qué suena ahora». What plays lives in the mini-player at
// the card's foot (mini.js), so Inicio never repeats it. Text + <img> elements only; the thumbs come from YouTube's
// public CDN, never a fetch from our JS.
import { el, emptyState, thumbUrl, tt } from "./shared.js";
import { avatar, chAct } from "./channel.js";
import { feedItem, itemSheet, skeleton } from "./feed.js";

export function fmtAge(ts){
  if(!ts) return "";
  const m = Math.max(0, Math.round((Date.now() / 1000 - Number(ts)) / 60));
  if(m < 1) return tt("age_now", null, "ahora mismo");
  if(m < 60) return tt("age_min", {n: m}, "hace " + m + " min");
  return tt("age_hour", {n: Math.round(m / 60)}, "hace " + Math.round(m / 60) + " h");
}

// The search box left Inicio (2026-11-17): the bar's 🔍 is the one door (search.js). Inicio is the results or the
// catalogue, rebuilt per render, then the blocked-channels line and the connect screens (V2-597).
export function buildHome(body){
  const home = el("div", "hb-yt-home");
  const blockedLine = el("div", "hb-yt-blocked", "");
  const conn = el("div", "hb-yt-conn");
  body.append(home, blockedLine, conn);
  return {home, blockedLine, conn};
}

function mkTile(it, extras){
  const tile = el("div", "hb-yt-tile");
  const img = document.createElement("img");
  img.loading = "lazy"; img.alt = "";
  const src = thumbUrl(it.videoId);
  if(src) img.src = src;
  tile.appendChild(img);
  (extras || []).forEach((x) => tile.appendChild(x));
  tile.appendChild(el("div", "hb-yt-tilet", it.title || "—"));
  if(it.channel) tile.appendChild(el("div", "hb-yt-tilec", it.channel));
  return tile;
}

// One catalogue row: a title, an optional «ver todo» that opens the tab, and a horizontal strip of cards.
function shelf(id, title, seeAll, items, extra){
  const sec = el("section", "hb-yt-shelf");
  sec.dataset.shelf = id;
  const head = el("div", "hb-yt-shelfh");
  head.appendChild(el("h3", "hb-yt-shelft", title));
  (extra || []).forEach((x) => head.appendChild(x));
  if(seeAll){
    const b = el("button", "hb-yt-seeall", seeAll.label || tt("see_all", null, "Ver todo"));
    b.type = "button";
    if(seeAll.title) b.title = seeAll.title;
    b.addEventListener("click", seeAll.run);
    head.appendChild(b);
  }
  sec.appendChild(head);
  if(!Array.isArray(items)){ sec.appendChild(items); return sec; }   // a feed: the suggestions, one column
  const row = el("div", "hb-yt-shrow");
  row.dataset.hpan = "";                                   // the strip scrolls sideways; the deck does not page on it
  items.forEach((x) => row.appendChild(x));
  sec.appendChild(row);
  return sec;
}

// The band of a search: ONE column of feed items, numbered for the voice; skeletons while the search is in flight.
function paintResults(home, root, data, ctx, res){
  if(data.adding){ home.appendChild(skeleton(4)); return; }
  const goPlayer = () => { if(root._hbYtSelectTab) root._hbYtSelectTab("player"); };
  const act = (n, p) => { if(ctx && ctx.action) ctx.action(n, p || {}); };
  const feed = el("div", "hb-yt-feed");
  res.forEach((it, i) => {
    const n = String(i + 1);
    const play = () => { act("play_result", {item: n}); goPlayer(); };
    feed.appendChild(feedItem(root, it, i + 1, {play,
      sheet: itemSheet(root, data, ctx, it, play, () => act("add_results", {items: n}))}));
  });
  home.appendChild(feed);
}

function paintCatalogue(home, root, data, ctx){
  const go = (tab) => { if(root._hbYtSelectTab) root._hbYtSelectTab(tab); };
  const act = (n, p) => { if(ctx && ctx.action) ctx.action(n, p || {}); };
  const loadTile = (it) => {
    const t = mkTile(it);
    t.addEventListener("click", () => { act("load", {videoId: it.videoId, title: it.title || ""}); go("player"); });
    return t;
  };
  let shown = 0;
  // The YouTube app's order (2026-11-17): his channels as round faces, what he watched lately, the feed, his lists.
  // 1 — HIS CHANNELS: the authors he follows (ours, V2-632); a tap opens the channel's own page.
  const cards = Array.isArray(data.channel_cards) ? data.channel_cards
    : (Array.isArray(data.channels) ? data.channels : []).filter((c) => c && c.name).map((c) => ({name: String(c.name)}));
  if(cards.length){
    home.appendChild(shelf("channels", tt("your_channels", null, "Tus canales"),
      {run: () => go("subs")}, cards.map((c) => {
        const b = el("button", "hb-yt-chtile");
        b.type = "button";
        b.title = tt("open_channel", {name: c.name}, "Abrir el canal {name}");
        b.append(avatar(c.avatar, c.name, true), el("span", "hb-yt-chtname", c.name));
        b.addEventListener("click", () => { go("subs"); chAct(root, ctx, "open_channel", {channel: c.name}, "refresh"); });
        return b;
      })));
    shown++;
  }
  // 2 — RECENTLY WATCHED: the library's history is ours (V2-604); «Ver todo» loads all of it into the queue.
  const hist = Array.isArray(data.history) ? data.history : [];
  if(hist.length){
    home.appendChild(shelf("history", tt("recent", null, "Vistos hace poco"),
      {title: tt("all_history_hint", null, "Carga el historial completo en la cola"), run: () => { act("show_history"); go("cola"); }},
      hist.slice(0, 12).map(loadTile)));
    shown++;
  }
  // 3 — NEW FROM HIS CHANNELS (V2-597): account-fed, pulled only when asked — the feed, full-width items.
  const sug = Array.isArray(data.suggested) ? data.suggested : [];
  const connectedAny = (Array.isArray(data.platforms) ? data.platforms : []).some((r) => r.connected);
  if(sug.length || connectedAny || data.suggesting){
    const bits = [];
    if(data.suggested_at) bits.push(fmtAge(data.suggested_at));
    if(data.suggested_channels) bits.push(tt("n_channels", {n: data.suggested_channels}, "{n} canales"));
    const sub = el("span", "hb-yt-sugsub", bits.length ? "· " + bits.join(" · ") : "");
    const rf = el("button", "hb-yt-seeall", data.suggesting ? tt("loading", null, "buscando…") : tt("refresh", null, "↻ refrescar"));
    rf.type = "button";
    rf.title = tt("refresh_hint", null, "Traer los vídeos recientes de tus suscripciones");
    rf.addEventListener("click", () => { if(!data.suggesting) act("suggest"); });
    const feed = el("div", "hb-yt-feed");
    sug.forEach((it) => {
      const play = () => { act("load", {videoId: it.videoId, title: it.title || ""}); go("player"); };
      const queue = () => act("add", {url: "https://www.youtube.com/watch?v=" + encodeURIComponent(it.videoId || "")});
      feed.appendChild(feedItem(root, it, 0, {play, sheet: itemSheet(root, data, ctx, it, play, queue)}));
    });
    const sec = shelf("suggested", tt("subs_suggestions", null, "Sugerencias de tus suscripciones"), null, feed, [rf]);
    sec.querySelector(".hb-yt-shelft").appendChild(sub);
    if(!sug.length && !data.suggesting)
      sec.appendChild(el("div", "hb-yt-note", tt("subs_empty", null, "Toca «refrescar» para traer los vídeos recientes de tus suscripciones.")));
    home.appendChild(sec);
    shown++;
  }
  // 4 — SAVED LISTS: one card per list, its first video's face; a tap opens it into the queue.
  const saved = (Array.isArray(data.lists) ? data.lists : []).filter((L) => L && String(L.name || "").trim());
  if(saved.length){
    home.appendChild(shelf("lists", tt("tab_lists", null, "Listas"), {run: () => go("listas")}, saved.map((L) => {
      const items = Array.isArray(L.items) ? L.items : [];
      const first = items.find((x) => x && x.videoId) || {};
      const t = mkTile({videoId: first.videoId, title: String(L.name).trim(),
                        channel: tt("n_videos", {n: items.length}, "{n} vídeos")});
      t.addEventListener("click", () => { act("open_list", {name: String(L.name).trim()}); go("cola"); });
      return t;
    })));
    shown++;
  }
  // The enforced preferences, spelled out (V2-604): a filter he cannot SEE is one he cannot trust.
  const prefs = data.prefs || {};
  const notes = Array.isArray(data.prefs_notes) ? data.prefs_notes : [];
  const pbits = [];
  if(prefs.min_definition) pbits.push(tt("min_def", {n: prefs.min_definition}, "mínimo {n}p"));
  if(prefs.captions === true) pbits.push(tt("cc_on", null, "subtítulos siempre"));
  if(prefs.captions === false) pbits.push(tt("cc_off", null, "sin subtítulos"));
  if(prefs.volume != null) pbits.push(tt("volume_n", {n: prefs.volume}, "volumen {n}"));
  notes.forEach((n) => { const t = String(n && n.text || "").trim(); if(t) pbits.push(tt("note", {text: t}, "nota: {text}")); });
  if(pbits.length) home.appendChild(el("div", "hb-yt-libp", pbits.join(" · ")));
  // Nothing at all: ONE honest empty state with the two ways in. Never «no video loaded» — a video may be playing
  // (its mini-player says so), the catalogue is simply still empty.
  if(!shown){
    home.appendChild(emptyState(tt("home_empty2", null, "Aún no hay nada en tu catálogo. Busca un vídeo, o conecta tu cuenta para traer tus suscripciones."), [
      {id: "search", label: tt("search_open", null, "Buscar vídeos"), run: () => { if(root._hbYtFocusSearch) root._hbYtFocusSearch(); }},
      {id: "connect", label: tt("connect_account", null, "Conectar la cuenta"),
       run: () => { const p = root.querySelector(".hb-yt-plug"); if(p) p.click(); }}]));
  }
}

export function paintHome(root, E, data, ctx){
  if(!E.home) return;
  E.home.textContent = "";
  const res = Array.isArray(data.search_results) ? data.search_results : [];
  // A live search IS Inicio: its results come first and alone; the catalogue returns when the bar's ← clears it
  // (a search that found nothing leaves the previous band in the store, so «no results» is never a state here).
  if(res.length || data.adding) paintResults(E.home, root, data, ctx, res);
  else paintCatalogue(E.home, root, data, ctx);
}
