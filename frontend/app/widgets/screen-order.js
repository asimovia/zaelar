// ============================================================================
// screen-order.js — a screen ANSWERS each canvas order the engine sends it (V2-907 §3.2).
//
// Every `widget/<op>` the engine emits carries a `seq` (`nucleo/acts/canvas.apply`). `services/sse.js` runs the op
// on its host as always and hands the op's result to `orderAck(host, d)`; the answer is read from the HOST'S OWN
// adapter before and after the op (`host._screen`, built by `desktop-screen.js` or the deck's), never from what the
// order asked for, and goes out at once through the host's screen reporter:
//   close <id>  → `done` when it left the screen, `not_open` when it was never there, else `refused`;
//   close all   → `done` when the screen is bare, `already_closed` when it already was;
//   show <id>   → `already_front` when it already was in front, `done` when it is on screen after, else `refused`;
//   anything else on an id the screen does not hold → `not_open`; an op that returned false → `refused`.
// An order nobody ran on this screen (the host's own report echoed back) is answered from the screen as it is.
// ============================================================================
import { reportAll } from "./screen-reporter.js?v=1";

export { reportAll };

const _where = (a, id) => (a.list().includes(id) ? a.vis(id) || "behind" : "");

function _answer(op, id, before, a, r) {
  const now = id ? _where(a, id) : "", ids = a.list();
  if (r === false || (r && r.ok === false)) return id && before.vis === "" ? "not_open" : "refused";
  if (op === "close") {
    if (!id) return before.ids.length === 0 ? "already_closed" : (ids.length === 0 ? "done" : "refused");
    return before.vis === "" ? "not_open" : (now === "" ? "done" : "refused");
  }
  if (op === "show") {
    if (before.vis === "front") return "already_front";
    // a show names the card as the engine knows it; the host may open it under its resolved id
    const moved = ids.some((x) => !before.ids.includes(x)) || _front(a) !== before.front;
    return now || moved ? "done" : "refused";
  }
  if (id && before.vis === "" && op !== "create") return "not_open";
  return "done";
}
const _front = (a) => a.list().find((x) => a.vis(x) === "front") || "";

/** Before `d`'s op runs on `host`: returns the function the op's result is handed to (once). An order with no `seq`,
 *  or a host with no screen document, answers nothing. */
export function orderAck(host, d) {
  const s = host && host._screen, seq = Number(d && d.seq);
  if (!s || !d || d.kind !== "widget" || !Number.isInteger(seq) || seq <= 0) return () => {};
  const a = s.adapter, id = String(d.id || ""), op = String(d.label || "");
  const before = { vis: id ? _where(a, id) : "", ids: a.list(), front: _front(a) };
  let said = false;
  const done = (result) => {
    if (said) return;
    said = true;
    Promise.resolve(result).catch(() => false).then((r) => { const why = _answer(op, id, before, a, r); s.rep.ack(seq, why === "done", why); });
  };
  // an op the event chain did not hand over (an echo of the screen's own report, an op with no host method):
  // answered from the screen as it stands once the chain has run
  setTimeout(() => done(undefined), 0);
  return done;
}
