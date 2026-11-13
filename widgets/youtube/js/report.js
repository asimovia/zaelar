// youtube widget — what the card SHOWS, said through the host's one door (`ctx.state`, V2-884 1a).
// The player's own events say whether it plays, which video, its sound and volume; the card says its face and the
// title it shows. Only CHANGES are sent (the player repeats its state several times a second); a new revision of the
// card's data is acked by a full snapshot only once applied and settled (`APPLY_GRACE_MS`, the player obeys an
// unmute asynchronously — C10 A2). The answer carries the engine's facts: the «tap for sound» hint follows them.
import { Y } from "./state.js";

export const APPLY_GRACE_MS = 1500;

function _paintFacts(facts){
  if(!Array.isArray(facts)) return;
  Y.facts = facts;
  if(typeof Y.paintHint === "function") Y.paintHint();
}

// What the card shows now; `applied` = the last pushed revision is applied (sends the whole snapshot with its ack).
export function reportState(patch, opts){
  const ctx = Y.ctx;
  if(!ctx || typeof ctx.state !== "function") return;
  const fresh = {};
  for(const k of Object.keys(patch || {})){
    const v = patch[k];
    if(v === undefined || v === null) continue;
    if(Y.shown[k] !== v){ Y.shown[k] = v; fresh[k] = v; }
  }
  const applied = !!(opts && opts.applied);
  if(!applied && !Object.keys(fresh).length) return;
  try{ Promise.resolve(ctx.state(applied ? Object.assign({}, Y.shown) : fresh, {applied})).then(_paintFacts); }catch(_){}
}

// Every render: the face and the title shown, and — when the data brought a new revision — its ack after the grace.
export function afterRender(data, ctx, tab, hasVid){
  Y.ctx = ctx;
  reportState({view: tab || "inicio", title: hasVid ? String(data.title || "").slice(0, 60) : ""});
  const r = data && data._rev;
  const key = r && r.epoch ? r.epoch + ":" + r.rev : "";
  if(key && key !== Y.revSeen){
    Y.revSeen = key;
    clearTimeout(Y.ackTimer);
    Y.ackTimer = setTimeout(() => reportState({}, {applied: true}), APPLY_GRACE_MS);
  }
}
