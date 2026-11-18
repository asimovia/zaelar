// ============================================================================
// mic-wire.js — what the microphone is ACTUALLY doing, as opposed to what the switch asks of it (2026-11-18).
//
// Measured on his engine (session af04be1f): the engine restarted, the screen came back, and the engine opened the
// speech recogniser and transcribed a sentence he was dictating somewhere else while he believed the mic was off. Two
// holes made it possible, and both live in the gap between INTENT and REALITY:
//   1. a reconnect PUBLISHED the capture track open and only then applied the stored switch — every frame in that
//      window left the browser;
//   2. the 🎤 drew the switch (and a fault slashed it too), never the track — so a mic that was sending could look
//      closed, and nothing on screen could ever show the two disagreeing.
//
// The two helpers below are the cure, kept dependency-free so a node test drives them with fakes:
//   publishMic → a capture is BORN in the switch's state: disabled and LiveKit-muted BEFORE it is published, so a
//                closed switch never has an «open for a moment» on the wire;
//   wireOpen   → the reality probe: true only while a published, unmuted, live, enabled capture exists — audio is
//                leaving this page. `services/mic.js` paints the icon from it.
// ============================================================================

/** Publish `track` (a MediaStreamTrack) already in the switch's state. `wrap` makes the SDK track, `publish` sends it. */
export async function publishMic({ track, closed, wrap, publish }) {
  if (!track) return null;
  track.enabled = !closed;                    // synchronous: the very first frame is already silent
  const local = wrap(track);
  if (closed && local && typeof local.mute === "function") await local.mute();   // the publication is born muted
  await publish(local);
  return local;
}

/** Is audio leaving this page right now? Read off the room's own publications, never off the switch. */
export function wireOpen(room) {
  const lp = room && room.localParticipant;
  const pubs = lp && lp.audioTrackPublications ? [...lp.audioTrackPublications.values()] : [];
  return pubs.some((p) => {
    const mt = p && !p.isMuted && p.track && p.track.mediaStreamTrack;
    return !!(mt && mt.readyState === "live" && mt.enabled);
  });
}

/** The level the SENDER reads off the published capture (getStats `media-source`), or null where the browser does not
 *  say — the proof a revived mic is heard by the wire, not only by the orb (2026-11-18, `mic-device.js` VERIFY_MS). */
export async function sentLevel(room) {
  try {
    const p = [...room.localParticipant.audioTrackPublications.values()][0];
    const st = await p.track.getRTCStatsReport();
    for (const r of st.values()) if (r.type === "media-source" && r.kind === "audio" && typeof r.audioLevel === "number") return r.audioLevel;
  } catch (_) {}
  return null;
}

/** A replaced track the sender does not carry (iOS after an interruption): unpublish (tracks kept) and publish anew. */
export async function republishMic({ room, track, closed, wrap }) {
  const lp = room && room.localParticipant;
  if (!lp || !track) return null;
  for (const p of [...lp.audioTrackPublications.values()]) { if (p.track) await lp.unpublishTrack(p.track, false); }
  return publishMic({ track, closed, wrap, publish: (lt) => lp.publishTrack(lt) });
}
