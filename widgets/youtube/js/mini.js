// youtube widget — THE MINI-PLAYER (V2-885): while a video is current and the Reproductor face is not the one shown,
// a bar at the foot of the CARD (inside it, never fixed to the page) says what plays and drives it — the music
// card's shape (widgets never import each other, V2-557, so the shape is copied, not the module).
//
// Operator, 2026-11-11: «si hay algo sonando, abajo del todo — como en el widget de música — los controles del
// reproductor con el vídeo en miniatura». Its visibility is CLASS-driven (style_cards.js): a tab change repaints no
// data, so a per-render display toggle would lag one click behind.
import { ICON_PLAY, ICON_PAUSE, ICON_NEXT, ICON_MUTED, ICON_VOL_UP, el, iconBtn, svgEl, halted, tt } from "./shared.js";
import { post } from "./player.js";

export function buildMini(root, ctx){
  const bar = el("div", "hb-yt-mini");
  bar.setAttribute("role", "region");
  bar.setAttribute("aria-label", tt("mini_label", null, "Reproduciendo"));
  const open = () => { if(root._hbYtSelectTab) root._hbYtSelectTab("player"); };
  const thumb = document.createElement("img");
  thumb.className = "hb-yt-mthumb"; thumb.alt = ""; thumb.loading = "lazy";
  const info = el("button", "hb-yt-minfo");
  info.type = "button";
  info.title = tt("mini_open", null, "Abrir el reproductor");
  const title = el("span", "hb-yt-mtitle", "");
  const chan = el("span", "hb-yt-mchan", "");
  info.append(title, chan);
  thumb.addEventListener("click", open);
  info.addEventListener("click", open);
  const play = iconBtn("hb-yt-mbtn main", ICON_PLAY, tt("play", null, "Play"));
  const next = iconBtn("hb-yt-mbtn", ICON_NEXT, tt("next", null, "Siguiente"),
                       () => { if(ctx && ctx.action) ctx.action("next"); });
  const mute = iconBtn("hb-yt-mbtn", ICON_MUTED, tt("mute", null, "Silencio"));
  bar.append(thumb, info, play, next, mute);
  root.appendChild(bar);
  return {bar, thumb, title, chan, play, mute};
}

export function paintMini(M, data, ctx, PL){
  if(!M || !M.bar) return;
  const vid = String(data.videoId || "");
  const thumbSrc = vid ? "https://i.ytimg.com/vi/" + encodeURIComponent(vid) + "/mqdefault.jpg" : "";
  if(M.thumb.getAttribute("src") !== thumbSrc){ if(thumbSrc) M.thumb.src = thumbSrc; else M.thumb.removeAttribute("src"); }
  M.title.textContent = data.title || "YouTube";
  M.chan.textContent = data.channel || "";
  const face = (b, markup, label) => {
    b.textContent = ""; b.appendChild(svgEl(markup)); b.title = label; b.setAttribute("aria-label", label);
  };
  face(M.play, data.paused ? ICON_PLAY : ICON_PAUSE, data.paused ? tt("play", null, "Play") : tt("pause", null, "Pausa"));
  M.play.onclick = (e) => { e.stopPropagation(); if(ctx && ctx.action) ctx.action(data.paused ? "play" : "pause"); };
  face(M.mute, data.muted ? ICON_VOL_UP : ICON_MUTED, data.muted ? tt("sound", null, "Sonido") : tt("mute", null, "Silencio"));
  const vol0 = Number(data.volume != null ? data.volume : 70);
  M.mute.onclick = (e) => {
    e.stopPropagation();
    // the same door as the player's own mute: the REAL click unlocks the browser's audio, gated on a stopped agent
    if(data.muted && !halted(ctx)){ post(PL, "unMute", []); post(PL, "setVolume", [vol0]); }
    if(ctx && ctx.action) ctx.action(data.muted ? "unmute" : "mute");
  };
}
