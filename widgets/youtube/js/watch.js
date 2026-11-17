// youtube widget — THE WATCH PAGE (2026-11-17, the YouTube app's own): under the video a thin seek bar with its
// times, the controls, the title over «channel · date» with Seguir, a row of action chips, and «A continuación» —
// what the queue plays next. The seek bar reads the PLAYER's own clock (the embed's `infoDelivery`, our <video>'s
// timeupdate: Y.tcur/Y.tdur, player.js) and a tap or a drag seeks through the one funnel (`post`) — his hand on the
// player, no server action, exactly like the embed's own scrubber. While his finger drags it the bar shows the drag
// (`Y.seekDrag`), never the clock the player keeps sending under it; and a stopped agent moves no player (V2-092).
import { Y } from "./state.js";
import { el, fmtTime, thumbUrl, halted, tt } from "./shared.js";
import { post } from "./player.js";

const PCT = () => (Y.tdur > 0 ? Math.max(0, Math.min(1, Y.tcur / Y.tdur)) : 0);

export function buildSeek(root, ctx){
  const box = el("div", "hb-yt-seek");
  const track = el("div", "hb-yt-strack");
  track.setAttribute("role", "slider");
  track.tabIndex = 0;
  const fill = el("div", "hb-yt-sfill");
  const knob = el("div", "hb-yt-sknob");
  track.append(fill, knob);
  const time = el("div", "hb-yt-stime", "");
  box.append(track, time);
  const pl = () => { const E = root._hbYtEls || {}; return E.video || E.iframe; };
  const at = (e) => { const r = track.getBoundingClientRect(); return Math.max(0, Math.min(1, (e.clientX - r.left) / (r.width || 1))); };
  const seek = (f) => {
    if(!(Y.tdur > 0) || halted(ctx)) return;
    Y.tcur = Math.round(f * Y.tdur);                    // the second the player is sent to is the one the bar says
    post(pl(), "seekTo", [Y.tcur, true]);
    paintClock(root);
  };
  track.addEventListener("pointerdown", (e) => {
    if(!(Y.tdur > 0) || halted(ctx)) return;
    e.stopPropagation();
    Y.seekDrag = at(e);
    try{ track.setPointerCapture(e.pointerId); }catch(_){}
    paintClock(root);
  });
  track.addEventListener("pointermove", (e) => { if(Y.seekDrag >= 0){ Y.seekDrag = at(e); paintClock(root); } });
  const end = () => { if(Y.seekDrag >= 0){ const f = Y.seekDrag; Y.seekDrag = -1; seek(f); } };
  track.addEventListener("pointerup", end);
  track.addEventListener("pointercancel", () => { Y.seekDrag = -1; paintClock(root); });
  track.addEventListener("keydown", (e) => {
    const step = e.key === "ArrowRight" ? 5 : e.key === "ArrowLeft" ? -5 : 0;
    if(step && Y.tdur > 0){ e.preventDefault(); seek(Math.max(0, Math.min(Y.tdur, Y.tcur + step)) / Y.tdur); }
  });
  return {box, track, fill, knob, time};
}

// The clock, painted on the seek bar and on the mini-player's progress line — his drag first, while there is one.
export function paintClock(root){
  const E = root._hbYtEls || {};
  const p = Y.seekDrag >= 0 ? Y.seekDrag : PCT();
  const S = E.seek;
  if(S){
    S.fill.style.width = (p * 100).toFixed(2) + "%";
    S.knob.style.left = (p * 100).toFixed(2) + "%";
    S.time.textContent = Y.tdur > 0 ? fmtTime(p * Y.tdur) + " / " + fmtTime(Y.tdur) : "";
    S.track.setAttribute("aria-label", tt("seek_label", null, "Posición del vídeo"));
    S.track.setAttribute("aria-valuemin", "0");
    S.track.setAttribute("aria-valuemax", String(Math.round(Y.tdur || 0)));
    S.track.setAttribute("aria-valuenow", String(Math.round(p * (Y.tdur || 0))));
    S.box.classList.toggle("off", !(Y.tdur > 0));
  }
  if(E.mini && E.mini.prog) E.mini.prog.style.width = (p * 100).toFixed(2) + "%";
}

// Title over «channel · date» and the Seguir chip; on a wide card the one line of V2-636 (title left, the rest right).
export function buildInfo(){
  const tline = el("div", "hb-yt-tline");
  const title = el("div", "hb-yt-title", "");
  const by = el("div", "hb-yt-by");
  const meta = el("div", "hb-yt-meta", "");
  const follow = el("button", "hb-yt-follow hb-btn hb-btn--sm");     // the kit's button: Seguir primary, Siguiendo quiet
  follow.type = "button";
  by.append(meta, follow);
  tline.append(title, by);
  return {tline, title, meta, follow};
}

// The action chips: captions, replay, block this channel. Scrolls sideways on the phone (`data-hpan`).
export function buildChips(root, ctx){
  const row = el("div", "hb-yt-wchips");
  row.dataset.hpan = ""; row.dataset.strip = "";
  const chip = (id, run) => {
    const b = el("button", "hb-yt-wchip");
    b.type = "button"; b.dataset.chip = id;
    b.addEventListener("click", run);
    row.appendChild(b);
    return b;
  };
  const act = (n, p) => { if(ctx && ctx.action) ctx.action(n, p || {}); };
  const cc = chip("captions", () => act((root._hbYtData || {}).captions ? "captions_off" : "captions_on"));
  chip("repeat", () => act("restart"));
  chip("block", () => act("block_channel", {}));
  const upnext = el("div", "hb-yt-upnext");
  return {row, cc, upnext};
}
// The chips' words, read from the bundle on every paint (V2-694: a language switch re-renders, never rebuilds).
function paintChips(row){
  const words = {captions: tt("captions", null, "Subtítulos"), repeat: tt("repeat", null, "Repetir"),
                 block: tt("block_channel", null, "Bloquear el canal")};
  row.querySelectorAll(".hb-yt-wchip").forEach((b) => { b.textContent = words[b.dataset.chip]; });
}

// Per render: the follow chip's state, captions lit, and what plays next (the queue after the current row).
export function paintWatch(root, E, data, ctx){
  const ch = String(data.channel || "");
  if(E.follow){
    const on = (Array.isArray(data.channels) ? data.channels : []).some((c) => c && c.name === ch);
    E.follow.textContent = on ? tt("following", null, "Siguiendo") : tt("follow", null, "Seguir");
    E.follow.classList.toggle("on", on);
    E.follow.classList.toggle("hb-btn--primary", !on); E.follow.classList.toggle("hb-btn--secondary", on);
    E.follow.hidden = !ch;
    E.follow.onclick = () => { if(ctx && ctx.action) ctx.action(on ? "unfollow_channel" : "follow_channel", {channel: ch}); };
  }
  if(E.cc){ E.cc.classList.toggle("on", !!data.captions); paintChips(E.cc.parentNode); }
  if(!E.upnext) return;
  const lst = Array.isArray(data.list) ? data.list : [];
  const pos = Number(data.pos != null ? data.pos : -1);
  const next = lst.map((it, i) => [it, i]).filter(([, i]) => i > pos).slice(0, 12);
  const sig = tt("up_next", null, "A continuación") + "|" +
    next.map(([it, i]) => i + ":" + (it.videoId || it.url || "") + ":" + (it.title || "")).join("|");
  if(E.upnext.dataset.sig === sig) return;
  E.upnext.dataset.sig = sig;
  E.upnext.textContent = "";
  E.upnext.hidden = !next.length;
  if(!next.length) return;
  E.upnext.appendChild(el("div", "hb-yt-unhead", tt("up_next", null, "A continuación")));
  next.forEach(([it, i]) => {
    const row = el("button", "hb-yt-unrow");
    row.type = "button";
    const img = document.createElement("img");
    img.loading = "lazy"; img.alt = "";
    const src = thumbUrl(it.videoId);
    if(src) img.src = src;
    const txt = el("span", "hb-yt-untext");
    txt.append(el("span", "hb-yt-untitle", it.title || it.url || "—"), el("span", "hb-yt-unchan", it.channel || ""));
    row.append(img, txt);
    row.addEventListener("click", () => { if(ctx && ctx.action) ctx.action("play_item", {item: String(i + 1)}); });
    E.upnext.appendChild(row);
  });
}
