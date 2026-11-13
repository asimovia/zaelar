// youtube — REAL YouTube player embedded in the canvas (an <iframe>, not a capture). Controlled by VOICE: data.py
// stores the desired command (last_cmd + cmd_seq) and state (paused/muted/volume); here we apply it to the player
// with postMessage (YouTube IFrame API, NO external library — only iframe messages). Contract: render(el, data, ctx).
// No network from JS: the <iframe> is an element, not our own request.

import { CSS } from "./js/style.js";
import { Y } from "./js/state.js";
import { el, _TABS, applyTabClass, tt } from "./js/shared.js";
import { applyCmd, buildFrame, bindReporters } from "./js/player.js";
import { afterRender, playerReplaced } from "./js/report.js";
import { paintAccount } from "./js/conn.js";
import { buildNav, paintNav } from "./js/nav.js";
import { buildMini, paintMini } from "./js/mini.js";
import { buildHomeHead, paintHomeHead, paintHome } from "./js/home.js";
import { renderSubs } from "./js/channel.js";
import { buildQueueBoxes, paintQueue, paintSavedLists } from "./js/lists.js";
import { buildControls, paintPlayer } from "./js/controls.js";

function injectStyles(){
  if(document.getElementById("hb-yt-css")) return;
  const s = document.createElement("style"); s.id = "hb-yt-css"; s.textContent = CSS; document.head.appendChild(s);
}

// (Re)builds the card's skeleton — the nav, the player frame and every face's container (moved out of
// render(), refactor2710-12 T-03; render() decides WHEN, exactly as before).
function buildCard(root, data, ctx, v){
  const {id, seq, loading, st, src, isStream, pkey, hasVid} = v;
  root.className = "hb-yt";
  root.textContent = "";
  // HOME vs PLAYER (V2-596): with no video loaded the card IS the home catalog; with one, the nav button
  // under the card header switches views WITHOUT unmounting the iframe (audio keeps playing while browsing —
  // remounting would cut it, the same reason the mobile Deck hides instead of unmounting).
  if(hasVid) root.classList.add("hb-yt-hasvid");
  // V2-632 — default tab: a video on screen means the player; nothing loaded means the dashboard. A tab the
  // operator already chose this page-life survives the rebuild (module-lived, like Y.screen) — EXCEPT that a
  // video ARRIVING on a card that had none jumps to the player: «ponme el vídeo de X» means watching it,
  // and leaving the dashboard up while it plays underneath is the confusion the redesign exists to end.
  if(!Y.tab) Y.tab = hasVid ? "player" : "inicio";
  if(hasVid && st && !st.key.slice(2) && !loading) Y.tab = "player";
  // V2-753 — and the MIRROR, which was never written: a video LEAVING a card that had one goes back
  // to the catalog. «Páralo, y vuelve al inicio» is one order, and `close` only did the first half —
  // the player emptied and the card sat on the now-blank Reproductor tab, which is exactly what he
  // reported twice: «y tampoco vuelves al inicio a ver el catálogo». Gated on the TRANSITION for the
  // same reason the jump above is: clicking «Reproductor» on an empty card is his choice and stands.
  if(!hasVid && st && st.key.slice(2) && !loading && Y.tab === "player") Y.tab = "inicio";
  applyTabClass(root);

  const {dots} = buildNav(root, ctx);                   // the bar: tabs · platform icons · plug · search (nav.js)
  // Everything under the bar lives in ONE scroll region, so the bar never scrolls away with the content.
  const body = el("div", "hb-yt-body");
  root.appendChild(body);

  const tline = el("div", "hb-yt-tline");           // V2-636: title left, channel/date right, ONE row
  const title = el("div", "hb-yt-title", data.title || "YouTube");
  tline.appendChild(title);
  const meta = el("div", "hb-yt-meta", "");          // channel · publication date (verifiable, V2-057)
  tline.appendChild(meta);
  body.appendChild(tline);
  // V2-634 — the playback-block banner: when the owner refuses embedding, the card SAYS what happened
  // (a swap of our own pick, or the honest «only on YouTube» for a pasted link) instead of leaving the
  // operator alone with the player's raw error screen. Filled per render from data.blocked_notice.
  const blockMsg = el("div", "hb-yt-blockmsg", "");
  body.appendChild(blockMsg);

  const {frame, iframe, video, unmuteHint} = buildFrame(data, ctx, loading, isStream, src, id);
  body.appendChild(frame);
  const {sInp, sClr, home, blockedLine, conn} = buildHomeHead(root, ctx, body);
  const {playBtn, muteBtn, vol} = buildControls(ctx, body);
  const {listBox, subsBox, listsBox, addInp, newList, nlNote, nlSave} = buildQueueBoxes(root, ctx, body);
  const mini = buildMini(root, ctx);                    // V2-885: the foot bar while a video is current off the player

  root._hbYt = { id: id, key: pkey, seq: seq, loading: loading };   // "load" is already covered by new src → do not re-post as command
  root._hbYtBuilt = true;
  root._hbYtEls = { iframe: iframe, video: video, title: title, meta: meta, blockMsg: blockMsg, vol: vol,
                    muteBtn: muteBtn, playBtn: playBtn, unmuteHint: unmuteHint,
                    listBox: listBox, home: home, blockedLine: blockedLine, dots: dots, conn: conn,
                    subsBox: subsBox, listsBox: listsBox, body: body,
                    sInp: sInp, sClr: sClr, addInp: addInp, newList: newList, nlNote: nlNote, nlSave: nlSave,
                    mini: mini };
}

export function render(root, data, ctx){
  Y.T = (ctx && typeof ctx.t === "function") ? ctx.t : null;
  injectStyles();
  data = data || {};
  const id = data.videoId || "";
  const seq = Number(data.cmd_seq || 0);
  const loading = !!data.loading;
  const st = root._hbYt || null;
  // V2-638 — a row can come from three places. `local`/`torrent` play through a plain <video src> (our own
  // library route, or the piece-aware torrent route while it still downloads); everything else is the embed.
  // The rebuild key covers BOTH: two different local files both carry videoId "", so keying on the id alone
  // would keep the first one mounted forever.
  const src = String(data.src || "");
  const isStream = !!src && (data.source === "local" || data.source === "torrent");
  const pkey = isStream ? ("s:" + src) : ("y:" + id);
  const hasVid = !!id || isStream;

  // (Re)build the card when the video changes, or when entering/leaving "searching" state (real bug 2026-07-23:
  // without this the card looked COMPLETELY empty while load searched YouTube, with no signal).
  if(!st || st.key !== pkey || st.loading !== loading || !root._hbYtBuilt){
    const replaced = !!st;                               // ANY rebuild destroys the player (a spinner, the same video)
    buildCard(root, data, ctx, {id, seq, loading, st, src, isStream, pkey, hasVid});
    if(replaced) playerReplaced(ctx, hasVid);             // V2-884 1a: the old player's state does not carry over
  }

  // Dynamic refresh on EVERY render (title, verifiable metadata, mute-toggle button, volume).
  const E = root._hbYtEls || {};
  root._hbYtData = data;
  // V2-638 — the control sites below address whichever player is mounted: a <video> for a library or
  // torrent row, the YouTube embed otherwise. `post` speaks both, so nothing else has to branch.
  const PL = E.video || E.iframe;
  paintNav(root, data);                                 // labels re-read per paint (V2-694), Cola wears its count
  paintHomeHead(E, data);
  paintAccount(root, E, data, ctx);
  paintPlayer(E, data, ctx, id, PL);
  paintMini(E.mini, data, ctx, PL);
  bindReporters(data, ctx, id, PL);
  paintQueue(root, E, data, ctx);
  paintHome(root, E, data, ctx);

  // SUBSCRIPTIONS tab — the channels as CARDS, and a click opens the channel's own PAGE (2026-09-29).
  if(E.subsBox) renderSubs(E.subsBox, root, data, ctx);

  // SAVED LISTS tab (V2-632).
  paintSavedLists(root, E, data, ctx);

  if(E.blockedLine){
    const blk = Array.isArray(data.blocked_channels) ? data.blocked_channels : [];
    E.blockedLine.textContent = blk.length ? tt("blocked_channels", {list: blk.join(", ")}, "🚫 Canales bloqueados: {list}") : "";
    E.blockedLine.style.display = blk.length ? "" : "none";
  }

  // Apply the last command if the counter advanced (same video; video changes are covered by the new src).
  if(seq !== root._hbYt.seq){
    applyCmd(PL, data, ctx);
    root._hbYt.seq = seq;
  }

  // V2-742 — «VUELVE AL CATÁLOGO», answered. It lives HERE, at the end of every render, and not up in
  // the rebuild branch: that branch only runs when the VIDEO changes, so an order given while the same
  // video keeps playing — which is the whole case, he is watching one and wants the list back — would
  // never have been read. Measured: written there first, three of this card's tests went red.
  //
  // It runs LAST on purpose, after the auto-jump to the player that a video's arrival triggers. Placed
  // before it, the jump would quietly undo every order he gives: a no-op that reports success.
  //
  // `selectTab` is the ONE transition (V2-626) and the card already exposes it, so this drives the same
  // rail his click drives rather than a second way to navigate.
  //
  // V2-755 — and since the data layer now writes this rail for «ponme el sexto» too (a video SWAPPING
  // is an arrival the transition above cannot see), the order is refused in ONE case: the player's face
  // with nothing in it. `goto_tab` is stored, `Y.gotoSeq` is module-lived, so a reload replays the last
  // order against a card whose video is gone — and an empty Reproductor is exactly the dead end V2-753
  // spent an initiative getting him out of.
  const _goto = data.goto_tab;
  if(_goto && _goto.seq && _goto.seq !== Y.gotoSeq){
    Y.gotoSeq = _goto.seq;                       // consumed — a re-render must not fight his hands
    const stale = _goto.tab === "player" && !hasVid;
    if(_TABS.indexOf(_goto.tab) >= 0 && root._hbYtSelectTab && !stale) root._hbYtSelectTab(_goto.tab);
  }
  afterRender(data, ctx, Y.tab, hasVid);                // V2-884 1a, LAST: the face after any change, the ack of its data
}
