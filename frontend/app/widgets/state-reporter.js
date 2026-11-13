// ============================================================================
// state-reporter.js — how a card's surface tells the engine what it SHOWS now (V2-884 C2, C10 A2/A3/A5).
//
// ONE module for the three hosts that build a card's `ctx` (the desktop card, the desktop activity rail and the
// phone's Deck): each mount makes one reporter and hands its `report` to the card as `ctx.state(patch, opts)`.
// The engine's door is `POST /widgets/{id}/state` (`widgets/state.py`); this side only says what it sees:
//
//   · a MOUNT is a surface — two tabs of one browser share the device id, so each mount draws its own id, counts
//     its own `n`, and starts with a FULL snapshot (a reload is a new mount);
//   · patches are coalesced (≤ 100 ms) and carry the LAST revision the card has APPLIED (`ack`). The host notes the
//     revision each data push carries (`seen`), and the card says when it has applied it and settled
//     (`ctx.state(fields, {applied: true})`): only then does a report ack it — a player that has not yet obeyed an
//     order must not confirm it (A2);
//   · a snapshot goes on `visibilitychange` (and with `sendBeacon` on hide/`pagehide`, when a phone pauses the page);
//   · the answer carries the engine's facts for this screen (`audio_blocked` …): `report` resolves to them, so the
//     card paints its own hint from them.
// Nothing here knows a card's fields: the card names them, the manifest declares them.
// ============================================================================

import { DEVICE } from "../services/api.js?v=2";

const COALESCE_MS = 100;
const _live = new Set();

function _onVisibility() {
  const hidden = document.visibilityState === "hidden";
  for (const r of _live) r._snapshot(hidden);
}
function _onPageHide() { for (const r of _live) r._snapshot(true); }
if (typeof document !== "undefined" && !globalThis.__hbStateReporterBound) {
  globalThis.__hbStateReporterBound = true;
  document.addEventListener("visibilitychange", _onVisibility);
  globalThis.addEventListener && globalThis.addEventListener("pagehide", _onPageHide);
}

// `baseId` is the app, `instance` the canvas id of this card (the app itself, or `app::x`).
export function stateReporter(baseId, instance, opts = {}) {
  const dev = opts.device || DEVICE;
  const post = opts.fetch || ((u, init) => fetch(u, init));
  const url = `/widgets/${baseId}/state`;
  const mount = Math.random().toString(36).slice(2, 12);
  let n = 0, full = true, timer = null, seen = null, ack = null, waiters = [];
  const last = {}, pending = {};

  const send = (beacon = false) => {
    clearTimeout(timer); timer = null;
    const patch = full ? { ...last } : { ...pending };
    for (const k of Object.keys(pending)) delete pending[k];
    n += 1;
    const body = { instance: instance || baseId, dev, mount, n, full, ack,
                   visible: typeof document === "undefined" || document.visibilityState !== "hidden", patch };
    full = false;
    const done = waiters; waiters = [];
    if (beacon && typeof navigator !== "undefined" && navigator.sendBeacon) {
      try { navigator.sendBeacon(url, new Blob([JSON.stringify(body)], { type: "application/json" })); } catch (_) {}
      done.forEach((w) => w(null));
      return;
    }
    Promise.resolve(post(url, { method: "POST", headers: { "Content-Type": "application/json" },
                                body: JSON.stringify(body), keepalive: true }))
      .then((r) => (r && r.json ? r.json() : null)).catch(() => null)
      .then((out) => { const facts = out && Array.isArray(out.facts) ? out.facts : null;
                       done.forEach((w) => w(facts)); });
  };
  const schedule = () => { if (!timer) timer = setTimeout(() => send(false), COALESCE_MS); };

  const rep = {
    mount,
    // The card's one door: what it shows now. `{applied: true}` = the last pushed revision is applied and settled.
    report(patch, o = {}) {
      for (const [k, v] of Object.entries(patch || {})) { last[k] = v; pending[k] = v; }
      if (o.applied && seen) { ack = seen; full = true; }
      const p = new Promise((res) => waiters.push(res));
      schedule();
      return p;
    },
    // The host: a data push carried revision `rev` ({epoch, rev}); the card has not applied it yet.
    seen(rev) { if (rev && rev.epoch && Number.isInteger(rev.rev)) seen = rev; },
    _snapshot(beacon) {
      if (!Object.keys(last).length) return;
      full = true;
      if (beacon) send(true); else schedule();
    },
    dispose() { clearTimeout(timer); _live.delete(rep); },
  };
  _live.add(rep);
  return rep;
}

// A host's one line per mount: the card (or rail) `w` gets a fresh reporter that has seen the data's revision.
export function mountState(w, baseId, id, data) {
  if (w._rep) w._rep.dispose();
  w._rep = stateReporter(baseId, id);
  w._rep.seen(data && data._rev);
  return w._rep;
}
