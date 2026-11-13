// youtube widget — what the card SHOWS, said through the host's one door (`ctx.state`, V2-884 1a).
// The player's own events say whether it plays, which video, its sound and volume; the card says its face and the
// title it shows. The protocol (a new player forgets the old one, the ack waits for the CURRENT player and its grace,
// a new mount starts clean) is the one every card's player shares (`/frontend/app/lib/player-report.js`); this module
// adds his hand on the embed and the facts' paint: the «tap for sound» hint and the gesture unlock.
import { playerReport } from "/frontend/app/lib/player-report.js";
import { Y } from "./state.js";

export const APPLY_GRACE_MS = 1500;
const SILENT_MS = 6000;                    // an embed's first word comes ~3 s after load (measured): twice that is silence
const PLAYER_FIELDS = ["playing", "playing_id", "muted", "volume"];
// HIS HAND on the player's own control (V2-884 1b). The player is a cross-origin iframe: a touch inside it gives it the
// focus (the page blurs); a <video> of ours takes a pointerdown. A sound or volume change within `HAND_MS` of that,
// renewed while he keeps moving it, is his — the only change the engine may adopt as his order. An autoplay start or a
// browser that reverts a sound on its own never comes with it.
const HAND_MS = 4000;
if(typeof window !== "undefined" && !window.__hbYtHandBound){
  window.__hbYtHandBound = true;
  const inPlayer = (n) => !!(n && n.closest && n.closest(".hb-yt-frame"));
  window.addEventListener("blur", () => setTimeout(() => { if(inPlayer(document.activeElement)) Y.handAt = Date.now(); }, 0));
  document.addEventListener("pointerdown", (e) => { if(inPlayer(e.target)) Y.handAt = Date.now(); }, true);
}
function _hand(){
  const now = Date.now(), on = now - (Y.handAt || 0) < HAND_MS;
  if(on) Y.handAt = now;                   // he keeps moving it (a volume drag): the window follows his hand
  return on;
}

function _paintFacts(facts){
  Y.facts = facts;
  if(typeof Y.paintHint === "function") Y.paintHint();
  if(facts.indexOf("audio_blocked") >= 0 && typeof Y.armUnlock === "function") Y.armUnlock();
}

const P = playerReport({fields: PLAYER_FIELDS, forget: ["playing_id", "muted", "volume"], graceMs: APPLY_GRACE_MS,
                        hand: (p) => ("muted" in p || "volume" in p) && _hand(), onFacts: _paintFacts,
                        silentMs: SILENT_MS});

// What the card shows now; `applied` = the last pushed revision is applied (the whole snapshot with its ack).
export function reportState(patch, opts){ P.report(patch, opts); }

// A new player (another video, a stream), or none (`hasVid` false: closed — what was rendered is acked, nothing waits).
export function playerReplaced(ctx, hasVid = true){ P.replaced(ctx, hasVid); }

// Every render, LAST (after any face change): the face and the title shown, and — when the data brought a new
// revision — its ack, once the current player has spoken.
export function afterRender(data, ctx, tab, hasVid){
  if(ctx !== P.state.ctx) Y.facts = [];   // a new mount: none of the old one's facts
  P.rendered(ctx, data && data._rev, hasVid,
             Object.assign({view: tab || "inicio"}, hasVid ? {title: String(data.title || "").slice(0, 60)} : {}),
             hasVid ? null : ["title"]);
}
