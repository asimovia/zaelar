// youtube widget — what the card SHOWS, said through the host's one door (`ctx.state`, V2-884 1a).
// The player's own events say whether it plays, which video, its sound and volume; the card says its face and the
// title it shows. What was already said is the MOUNT's memory (the host's reporter dedupes), never this module's: a
// card reopened on the same page says everything again. A new player (another video) first says it does not play and
// forgets what the old one said; a new revision is acked by a full snapshot only after the CURRENT player has spoken
// and settled (`APPLY_GRACE_MS`, the player obeys an unmute asynchronously — C10 A2). The answer carries the engine's
// facts: the «tap for sound» hint and the gesture unlock follow them.
import { Y } from "./state.js";

export const APPLY_GRACE_MS = 1500;
const PLAYER_FIELDS = ["playing", "playing_id", "muted", "volume"];

function _paintFacts(facts){
  if(!Array.isArray(facts)) return;
  Y.facts = facts;
  if(typeof Y.paintHint === "function") Y.paintHint();
  if(facts.indexOf("audio_blocked") >= 0 && typeof Y.armUnlock === "function") Y.armUnlock();
}

function _ackLater(){
  clearTimeout(Y.ackTimer);
  const ctx = Y.ctx;
  Y.ackTimer = setTimeout(() => { if(Y.ctx === ctx) reportState({}, {applied: true}); }, APPLY_GRACE_MS);
}

// What the card shows now; `applied` = the last pushed revision is applied (the whole snapshot with its ack).
export function reportState(patch, opts){
  const ctx = Y.ctx;
  if(!ctx || typeof ctx.state !== "function") return;
  // the player spoke: a revision waiting for the CURRENT player is acked from here, after its grace
  if(Y.ackWaits && Object.keys(patch || {}).some((k) => PLAYER_FIELDS.indexOf(k) >= 0)){ Y.ackWaits = false; _ackLater(); }
  try{ Promise.resolve(ctx.state(patch || {}, opts || {})).then(_paintFacts); }catch(_){}
}

// A new player (another video, a stream, or none): it does not play yet and nothing the old one said stands.
export function playerReplaced(){
  clearTimeout(Y.ackTimer); Y.ackWaits = false;
  reportState({playing: false}, {forget: ["playing_id", "muted", "volume"]});
  Y.ackWaits = true;                       // AFTER its own report: only the NEW player's first word starts the ack
}

// Every render, LAST (after any face change): the face and the title shown, and — when the data brought a new
// revision — its ack, once the current player has spoken.
export function afterRender(data, ctx, tab, hasVid){
  if(ctx !== Y.ctx){                       // a new mount: nothing of the old one's revision or facts carries over
    clearTimeout(Y.ackTimer); Y.ctx = ctx; Y.revSeen = ""; Y.facts = []; Y.ackWaits = !!hasVid;   // its player will speak
  }
  reportState(Object.assign({view: tab || "inicio"}, hasVid ? {title: String(data.title || "").slice(0, 60)} : {}),
              hasVid ? {} : {forget: ["title"]});
  const r = data && data._rev;
  const key = r && r.epoch ? r.epoch + ":" + r.rev : "";
  if(key && key !== Y.revSeen){
    Y.revSeen = key;
    if(!Y.ackWaits) _ackLater();
  }
}
