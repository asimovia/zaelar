// youtube widget — THE FEED ITEM (2026-11-17, the YouTube app's own): search results and suggestions as ONE column of
// full-width 16:9 pictures with the duration in a corner, then the ordinal (small, muted: voice and eye share one index
// — «pon el tercero»), the title on two lines, «channel · age» and a ⋮ that opens the row's sheet. A container 600px
// and wider turns the same item into a row, picture left (style_phone.js). Loading is skeleton items, never «0 results».
import { el, thumbUrl, tt } from "./shared.js";
import { openSheet, moreBtn } from "./sheet.js";

// `it` = a row of the band; `n` = its 1-based ordinal or 0; `o` = {play, sheet: [{label, run}]}.
export function feedItem(root, it, n, o){
  const item = el("div", "hb-yt-item");
  item.tabIndex = 0;                                    // the row plays on Enter; its ⋮ is the one control inside it
  const pic = el("div", "hb-yt-ithumb");
  const img = document.createElement("img");
  img.loading = "lazy"; img.alt = "";
  const src = thumbUrl(it.videoId);
  if(src) img.src = src;
  pic.appendChild(img);
  if(it.duration) pic.appendChild(el("span", "hb-yt-dur", it.duration));
  const text = el("div", "hb-yt-itext");
  const title = el("div", "hb-yt-ititle");
  if(n) title.appendChild(el("span", "hb-yt-rnum", String(n)));
  title.appendChild(document.createTextNode(it.title || "—"));
  text.appendChild(title);
  const sub = [it.channel, it.published].filter(Boolean).join(" · ");
  if(sub) text.appendChild(el("div", "hb-yt-imeta", sub));
  item.append(pic, text, moreBtn("hb-yt-imore", tt("more_actions", null, "Más acciones"),
                                 (b) => openSheet(root, it.title || "", o.sheet, b)));
  item.addEventListener("click", o.play);
  item.addEventListener("keydown", (e) => { if(e.key === "Enter" && e.target === item) o.play(); });
  return item;
}

// The sheet of a row he could add or follow from. `play` plays it, `queue` puts it in the queue without playing.
export function itemSheet(root, data, ctx, it, play, queue){
  const act = (n, p) => { if(ctx && ctx.action) ctx.action(n, p || {}); };
  const ch = String(it.channel || "");
  const followed = (Array.isArray(data.channels) ? data.channels : []).some((c) => c && c.name === ch);
  const opts = [{id: "play", label: tt("play", null, "Reproducir"), run: play},
                {id: "queue", label: tt("add_to_queue", null, "Añadir a la cola"), run: queue}];
  if(ch){
    opts.push(followed ? {id: "unfollow", label: tt("unfollow_channel", null, "Dejar de seguir el canal"), run: () => act("unfollow_channel", {channel: ch})}
                       : {id: "follow", label: tt("follow_channel", null, "Seguir el canal"), run: () => act("follow_channel", {channel: ch})});
    opts.push({id: "block", label: tt("block_channel", null, "Bloquear el canal"), run: () => act("block_channel", {channel: ch})});
  }
  return opts;
}

// While a search is in flight: grey items in the shape of what is coming.
export function skeleton(n){
  const box = el("div", "hb-yt-feed hb-yt-skels");
  box.setAttribute("aria-busy", "true");
  for(let i = 0; i < n; i++){
    const item = el("div", "hb-yt-item hb-yt-skel");
    const text = el("div", "hb-yt-itext");
    text.append(el("div", "hb-yt-iline"), el("div", "hb-yt-iline short"));
    item.append(el("div", "hb-yt-ithumb"), text);
    box.appendChild(item);
  }
  return box;
}
