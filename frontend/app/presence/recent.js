// recent.js — what the face did and what it saw in the last seconds (V2-928, the operator 2026-11-18: «if he asks why
// you smiled, the model must find in the state what just happened»). Two kinds of entry, by NAME only:
//   saw  — a gesture of his the face perceived on the device (humanity/perceive.js: smile, wink, tongue…); whether the
//          face answered it is told by the `did` that PLAYED (the engine pairs them), never by an intention;
//   did  — a gesture of the face's own that has a REASON: an answer to his (`why: "answer"`, `of`: what it answered) or
//          a nod / shake while saying yes or no (`why: "said_yes" | "said_no"`).
// The face's idle life (glances, its resting smile) is not recorded: it has no reason to tell. The screen reports the
// list to the engine (PresenceLayer.js → api.screensFace), which words it for the model; no image, no number about a
// face ever goes — only these names and their age in seconds.

export const RECENT = { windowMs: 30000, max: 8 };
let items = [];
const subs = new Set();

/** Record one entry: `note("saw", "smile", {answered: true})`, `note("did", "wink", {why: "answer", of: "wink"})`. */
export function note(kind, name, extra = {}) {   // `extra`: `{why, of}` for a `did`
  const it = { kind, name, ...extra, at: Date.now() };
  items.push(it);
  items = items.filter((x) => it.at - x.at <= RECENT.windowMs).slice(-RECENT.max);
  for (const f of subs) { try { f(it); } catch (_) {} }
}

/** The entries of the window, oldest first, with their age in whole seconds (what the engine receives). */
export function recent(now = Date.now()) {
  return items.filter((x) => now - x.at <= RECENT.windowMs).map(({ at, ...x }) => ({ ...x, age_s: Math.round((now - at) / 1000) }));
}

/** Called after each new entry. → unsubscribe. */
export function onNote(fn) { subs.add(fn); return () => subs.delete(fn); }

/** Forget the entries of one kind, or all (the camera went off: what it saw goes; a test starts over). Tells the
 *  subscribers, so the engine lets go of them too. */
export function clear(kind = null) {
  items = kind ? items.filter((x) => x.kind !== kind) : [];
  for (const f of subs) { try { f(null); } catch (_) {} }
}
