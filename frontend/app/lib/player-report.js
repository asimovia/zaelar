// ============================================================================
// player-report.js — what a PLAYER inside a card says through the card's one state door (V2-884 C2, C10 A2).
//
// One protocol for every app that holds a player (the video card's embed and <video>, the music card's hidden embed
// and <audio>), so the subtle part is written once:
//   · a player's events are reported as they happen (`report`); the host's reporter dedupes per mount;
//   · a NEW player (another song, a rebuilt frame, a stream) first says it does not play and forgets what the old one
//     said (`replaced`), and the next revision is acked only after the CURRENT player has spoken;
//   · a new revision is acked by a full snapshot `graceMs` after that (the player obeys an unmute asynchronously);
//   · a new mount (`rendered` with another ctx) starts with nothing of the old one's revision or facts;
//   · the door's answer carries the engine's facts: `onFacts` paints them (a «tap for sound» hint).
// `hand(patch)` says whether HIS hand moved the player for this change (only that may be adopted as his order).
// `silentMs`: a new player that has not said a word by then says it does not play (a phone that holds the embed back,
// a video its owner refuses), so the revision is acked and the engine reads «not playing», never «unknown» for ever;
// `quiet()` true skips it (the agent stopped: nothing was meant to play).
// Nothing here knows an app's fields beyond the names it is given.
// ============================================================================

export function playerReport({ fields = [], forget = [], graceMs = 1500, hand = null, onFacts = null, silentMs = 0,
                               quiet = null } = {}) {
  const S = { ctx: null, revSeen: "", facts: [], ackWaits: false, ackTimer: null, silence: null };

  const awaitWord = () => {                // the ack waits for the player's first word — or its silence, said
    S.ackWaits = true;
    clearTimeout(S.silence);
    const ctx = S.ctx;
    if (silentMs) S.silence = setTimeout(() => {
      if (S.ctx === ctx && S.ackWaits && !(typeof quiet === "function" && quiet())) report({ playing: false });
    }, silentMs);
  };

  const ackLater = () => {
    clearTimeout(S.ackTimer);
    const ctx = S.ctx;
    S.ackTimer = setTimeout(() => { if (S.ctx === ctx) report({}, { applied: true }); }, graceMs);
  };

  function report(patch, opts) {
    const ctx = S.ctx, p = patch || {};
    if (!ctx || typeof ctx.state !== "function") return;
    // the player spoke: a revision waiting for the CURRENT player is acked from here, after its grace
    if (S.ackWaits && Object.keys(p).some((k) => fields.indexOf(k) >= 0)) { S.ackWaits = false; ackLater(); }
    const o = Object.assign({}, opts || {});
    if (typeof hand === "function" && hand(p)) o.hand = true;
    try {
      Promise.resolve(ctx.state(p, o)).then((f) => {
        if (!Array.isArray(f)) return;
        S.facts = f;
        if (typeof onFacts === "function") onFacts(f);
      });
    } catch (_) {}
  }

  // A new player, or none (`waits` false): it does not play yet and nothing the old one said stands. With no player
  // there is nothing to wait for: what was rendered is acked after the grace.
  function replaced(ctx, waits = true) {
    if (ctx) S.ctx = ctx;
    clearTimeout(S.ackTimer); S.ackWaits = false;
    report({ playing: false }, { forget });
    if (waits) awaitWord();                // AFTER its own report: only the NEW player's first word starts the ack
    else if (S.revSeen) ackLater();
  }

  // Every render: the face the card shows (`face`, `faceForget`) and — when the data brought a new revision — its ack,
  // once the current player has spoken (a player replaced later in the same render takes the ack over).
  function rendered(ctx, rev, hasPlayer, face, faceForget) {
    if (ctx !== S.ctx) {                   // a new mount: nothing of the old one's revision or facts carries over
      clearTimeout(S.ackTimer); S.ctx = ctx; S.revSeen = ""; S.facts = []; S.ackWaits = false;
      if (hasPlayer) awaitWord();
    }
    if (face) report(face, faceForget && faceForget.length ? { forget: faceForget } : {});
    const key = rev && rev.epoch ? rev.epoch + ":" + rev.rev : "";
    if (key && key !== S.revSeen) {
      S.revSeen = key;
      if (!S.ackWaits) ackLater();
    }
  }

  return { report, replaced, rendered, state: S };
}
