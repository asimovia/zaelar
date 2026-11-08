// outbox.js — a typed line is HIS, and it is kept until the engine says it has it (operator, 2026-11-08).
//
// Measured: he typed a request while the engine was stalled (the machine out of memory); it went down the room's
// data channel, which never says whether anything received it, the agent had just dropped, and the in-memory queue
// died with the reload — the wall showed his line, the engine never saw it, and the next session greeted him.
//
// Every line now goes over HTTP (`POST /api/chat`, which answers), is kept in this browser's storage until that
// answer is `ok`, and is tried again: when a session comes up, every few seconds while it waits, and after a reload.
// A line older than the TTL is not sent — an order from a quarter of an hour ago is not an order any more.
//
// Pure: storage, the sender, the clock and the timer are handed in, so it runs the same in a test.

export const OUTBOX_KEY = "hb_outbox_v1";
export const OUTBOX_TTL_MS = 15 * 60 * 1000;

export function createOutbox({ storage, send, onNoSession, now = () => Date.now(),
                               schedule = (fn, ms) => setTimeout(fn, ms) }) {
  let draining = false, timer = null;

  function load() {
    try {
      const xs = JSON.parse(storage.getItem(OUTBOX_KEY) || "[]");
      const t = now();
      return Array.isArray(xs) ? xs.filter((x) => x && x.t && t - (x.at || 0) < OUTBOX_TTL_MS) : [];
    } catch (_) { return []; }
  }
  function save(xs) { try { storage.setItem(OUTBOX_KEY, JSON.stringify(xs)); } catch (_) {} }
  function later(ms) {
    if (timer) return;
    timer = schedule(() => { timer = null; drain(); }, ms);
  }

  async function drain() {
    if (draining) return;
    draining = true;
    try {
      let xs = load();
      save(xs);                                     // what aged out leaves now
      while (xs.length) {
        const head = xs[0];
        let r = null;
        try { r = await send(head.t); } catch (_) { r = { ok: false, reason: "network" }; }
        if ((r && r.ok) || (r && r.reason === "empty")) {
          xs = load().filter((x) => x.id !== head.id);
          save(xs);
          continue;
        }
        // no session yet → bring one up (it answers the line once it has started) · stopped / network → wait
        if (r && r.reason === "no_session" && onNoSession) onNoSession();
        later(r && r.reason === "stopped" ? 10000 : 3000);
        break;
      }
    } finally { draining = false; }
  }

  function add(text) {
    const t = String(text || "").trim();
    if (!t) return false;
    const xs = load();
    xs.push({ id: now().toString(36) + Math.random().toString(36).slice(2, 7), t, at: now() });
    save(xs);
    drain();
    return true;
  }

  return { add, drain, size: () => load().length, later };
}
