// debug-fold.js — which flow an event of the Traces view belongs to, read from two DECLARED fields of the engine's
// events (`nucleo/conversation_host/turns.py`), never from an id's shape:
//
//   · a `trace merge` marker carries `merge_into`: its trace is FOLDED into that one (chains resolve transitively);
//   · a `flow end` carrying `discarded` is an intervention the ear discarded: never a flow, only counted.
//
// A trace that has not been shown yet and so far carries only the ear's own events (`conv_ear`) is HELD: an
// intervention still being heard is not a flow until the inbox accepts it (folded into its turn) or the ear
// discards it. Anything else arriving for it releases it as a flow of its own.
export const EAR_KIND = "conv_ear";

export function createFold() {
  const into = new Map();       // trace -> the trace it was folded into
  const held = new Map();       // trace -> its events, while it is only the ear's
  const discards = { n: 0, last: [] };   // how many the ear discarded, and the latest {trace, why, at}
  const KEEP = 50;

  function resolve(tid) {
    let cur = tid;
    const seen = new Set();
    while (into.has(cur) && !seen.has(cur)) { seen.add(cur); cur = into.get(cur); }
    return cur;
  }

  // What to do with one event: {act: "fold", from, to, events} · {act: "discard", trace} ·
  // {act: "hold"} · {act: "show", trace, events} (events: the held ones to show first, then this one).
  function route(d, shown) {
    const raw = String(d.trace || "");
    if (d.kind === "trace" && d.label === "merge" && d.merge_into) {
      const from = resolve(raw), to = resolve(String(d.merge_into));
      if (!from || from === to) return { act: "hold" };
      into.set(from, to);
      const events = held.get(from) || [];
      held.delete(from);
      return { act: "fold", from, to, events };
    }
    const tid = resolve(raw);
    if (d.kind === "flow" && d.label === "end" && d.discarded) {
      held.delete(tid);
      discards.n++;
      discards.last.push({ trace: tid, why: String(d.discarded), at: d._rx || Date.now() });
      if (discards.last.length > KEEP) discards.last.shift();
      return { act: "discard", trace: tid };
    }
    if (!shown(tid) && d.kind === EAR_KIND) {
      if (!held.has(tid)) held.set(tid, []);
      held.get(tid).push(d);
      return { act: "hold" };
    }
    const events = held.get(tid) || [];
    held.delete(tid);
    return { act: "show", trace: tid, events: events.concat([d]) };
  }

  function clear() { into.clear(); held.clear(); discards.n = 0; discards.last.length = 0; }

  return { route, resolve, discards, clear };
}
