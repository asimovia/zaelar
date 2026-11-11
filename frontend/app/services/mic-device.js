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

/** `acquire()` → a fresh MediaStream; `adopt(stream)` swaps it into the session; `log(what, err)` is the audit. */
export function createMicDevice({ acquire, adopt, log = () => {} }) {
  let released = false, pending = null;
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
    /** Ask for the device again and adopt it. `isStale()` is read once the browser answered: a session stopped, or
     *  the mic closed again, meanwhile — the fresh stream is closed at once and the device stays released. */
    reacquire(isStale = () => false) {
      if (!released) return Promise.resolve(false);
      if (pending) return pending;
      pending = (async () => {
        try {
          const fresh = await acquire();
          if (isStale()) { try { fresh.getTracks().forEach((tr) => tr.stop()); } catch (_) {} return false; }
          await adopt(fresh);
          released = false;
          log("reopened");
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
