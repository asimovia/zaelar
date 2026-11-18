// ============================================================================
// mic-device.js — a CLOSED microphone releases the DEVICE, not only the wire (2026-11-11).
//
// The 🎤 switch (`mic.js`) used to silence the capture track (`enabled = false`) and mute the publication. The wire
// went quiet, but the browser kept the device open: the red recording dot stayed lit over a microphone the operator
// had closed. So closing it now STOPS the capture tracks, which hands the device back, and opening it asks the browser
// for the same device again (permission already given: no sheet) and swaps the new track into the publication.
//
// The wake-word PARK is not this: it never touches the device (a parked mic has to come back without clipping the
// first words after the name). Only the operator's own switch releases.
//
// No imports on purpose: the session engine hands in how to acquire and adopt a stream, and a node test drives it.
// ============================================================================

// REVIVE (2026-11-16). The system can take the device too: iOS ends the capture track when it interrupts the audio
// session, and the page kept publishing a dead track. `revive()` is the same reacquire for a track the SYSTEM lost
// (the mic stays open: he never closed it), bounded — `REVIVE_MAX` tries in `REVIVE_WINDOW_MS` — so a device that
// keeps dying is left red for his tap instead of being asked for in a loop.
export const REVIVE_MAX = 3;
export const REVIVE_WINDOW_MS = 60000;
// 2026-11-18 — A REVIVE IS PROVED, NOT ASSUMED. Measured on iOS (b154): a revive during an audio interruption got a
// track born muted by its source, swapped it into the sender and logged «reopened»; the analyser then heard him while
// the server got 44 chunks of pure silence. So the old tracks are stopped before the device is asked for again, and a
// revived capture must show audio leaving within `VERIFY_MS` (`probe()` → {ended, muted, level}; level = the sender's
// own reading, null where the browser does not say). Not flowing → republished once; still not → the session restarts.
export const VERIFY_MS = 2500;
export const VERIFY_STEP_MS = 250;

/** `acquire()` → a fresh MediaStream; `adopt(stream)` swaps it into the session; `log(what, err)` is the audit.
 *  `current()` is the stream in use; `probe`/`republish`/`restart` prove and escalate a revive (all optional). */
export function createMicDevice({ acquire, adopt, log = () => {}, now = () => Date.now(), current = () => null,
                                  probe = null, republish = null, restart = null,
                                  wait = (ms) => new Promise((r) => setTimeout(r, ms)) }) {
  let released = false, pending = null, revives = [];
  async function flows() {
    for (let t = 0; ; t += VERIFY_STEP_MS) {
      const p = await probe();
      if (!p || p.ended) return false;
      if (!p.muted && (p.level == null || p.level > 0)) return true;
      if (t >= VERIFY_MS) return false;
      await wait(VERIFY_STEP_MS);
    }
  }
  async function proved(isStale) {
    if (!probe) return true;
    const born = await probe();
    if (born && !born.muted && await flows()) return true;
    if (isStale() || !republish) return false;
    log(born && born.muted ? "republish_born_muted" : "republish_silent");
    await republish();
    return flows();
  }
  return {
    released: () => released,
    /** A new capture (a session start) owns the device again. */
    reset() { released = false; },
    /** Stop the capture tracks: the browser releases the device. A chat-only session's silent stream holds none. */
    release(stream) {
      if (released || !stream || stream.__silent) return false;
      try { stream.getAudioTracks().forEach((tr) => tr.stop()); } catch (_) {}
      released = true;
      log("released");
      return true;
    },
    /** The system lost the track: take the device again (bounded). `force` = his tap, which always gets a try. */
    revive(isStale = () => false, { force = false } = {}) {
      if (pending) return pending;   // one revive at a time: a second loss while one is being proved is the same loss
      const t = now();
      revives = revives.filter((at) => t - at < REVIVE_WINDOW_MS);
      if (!force && revives.length >= REVIVE_MAX) { log("revive_bounded"); return Promise.resolve(false); }
      revives.push(t);
      const old = current();
      if (old && !old.__silent) { try { old.getAudioTracks().forEach((tr) => tr.stop()); } catch (_) {} }
      released = true;
      log("revive");
      return this.reacquire(isStale, { prove: true });
    },
    /** Ask for the device again and adopt it. `isStale()` is read once the browser answered: a session stopped, or
     *  the mic closed again, meanwhile — the fresh stream is closed at once and the device stays released. */
    reacquire(isStale = () => false, { prove = false } = {}) {
      if (!released) return Promise.resolve(false);
      if (pending) return pending;
      pending = (async () => {
        try {
          const fresh = await acquire();
          if (isStale()) { try { fresh.getTracks().forEach((tr) => tr.stop()); } catch (_) {} return false; }
          await adopt(fresh);
          released = false;
          if (!prove) { log("reacquired"); return true; }
          if (await proved(isStale)) { log("reopened"); return true; }
          if (isStale() || !restart) { log("not_flowing"); return false; }
          log("restart");
          await restart();
          return true;
        } catch (e) {
          log("reopen_failed", e);
          return false;
        } finally {
          pending = null;
        }
      })();
      return pending;
    },
  };
}
