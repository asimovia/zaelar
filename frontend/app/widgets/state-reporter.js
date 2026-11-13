// ============================================================================
// state-reporter.js — how a card's surface tells the engine what it SHOWS now (V2-884 C2, C10 A2/A3/A5).
//
// ONE module for the three hosts that build a card's `ctx` (the desktop card, the desktop activity rail and the
// phone's Deck): each mount makes one reporter and hands its `report` to the card as `ctx.state(patch, opts)`.
// The engine's door is `POST /widgets/{id}/state` (`widgets/state.py`); this side only says what it sees:
//
//   · a MOUNT is a surface — two tabs of one browser share the device id, so each mount draws its own id, counts
//     its own `n`, and starts with a FULL snapshot (a reload is a new mount). What it already said is remembered
//     HERE, per mount, so a card reopened on the same page says everything again (V2-884 1a audit P1-1);
//   · only CHANGES are sent, coalesced (≤ 100 ms), one POST in flight at a time; a failed or crossed POST makes the
//     next one a full snapshot (never a value lost because it was marked sent);
//   · a report carries the LAST revision the card has APPLIED (`ack`). The host notes the revision each data push
//     carries (`seen`); the card says when it has applied it and settled (`{applied: true}`) — only then does a
//     report ack it (A2). `{forget: [...]}` drops fields the card can no longer vouch for (a new player);
//   · a snapshot on `visibilitychange`, with `sendBeacon` on hide/`pagehide` (marked not visible), and on every
//     reopening of the event stream (`snapshotAll`, called by `services/sse.js`);
//   · a mount replaced by a newer tab that becomes visible again takes the screen back with a new mount (A3);
//   · the answer carries the engine's facts for this screen: `report` resolves to them.
// `dispose()` ends the mount: nothing is sent after it. Nothing here knows a card's fields.
// ============================================================================

import { DEVICE } from "../services/api.js?v=2";

const COALESCE_MS = 100;
const _live = new Set();

function _onVisibility() {
  const hidden = document.visibilityState === "hidden";
  for (const r of _live) r._snapshot(hidden, !hidden);
}
function _onPageHide() { for (const r of _live) r._snapshot(true); }
if (typeof document !== "undefined" && !globalThis.__hbStateReporterBound) {
  globalThis.__hbStateReporterBound = true;
  document.addEventListener("visibilitychange", _onVisibility);
  globalThis.addEventListener && globalThis.addEventListener("pagehide", _onPageHide);
}

// The event stream reopened (a reconnect, an engine restart): every live mount says everything again.
export function snapshotAll() { for (const r of _live) r._snapshot(false); }

const _newMount = () => Math.random().toString(36).slice(2, 12);

// `baseId` is the app, `instance` the canvas id of this card (the app itself, or `app::x`).
export function stateReporter(baseId, instance, opts = {}) {
  const dev = opts.device || DEVICE;
  const post = opts.fetch || ((u, init) => fetch(u, init));
  const url = `/widgets/${baseId}/state`;
  let mount = _newMount(), n = 0, full = true, timer = null, seen = null, ack = null, waiters = [];
  let dead = false, flying = false, again = false, lastFacts = null, retaken = false;
  const last = {}, pending = {};

  const body = (beacon) => {
    n += 1;
    const patch = full ? { ...last } : { ...pending };
    for (const k of Object.keys(pending)) delete pending[k];
    const b = { instance: instance || baseId, dev, mount, n, full, ack, patch,
                visible: !beacon && (typeof document === "undefined" || document.visibilityState !== "hidden") };
    full = false;
    return b;
  };
  const settle = (facts) => { if (facts) lastFacts = facts; const w = waiters; waiters = []; w.forEach((f) => f(facts)); };

  const send = (beacon = false) => {
    clearTimeout(timer); timer = null;
    if (dead) return settle(null);
    if (beacon) {
      try { if (typeof navigator !== "undefined" && navigator.sendBeacon) {
        navigator.sendBeacon(url, new Blob([JSON.stringify(body(true))], { type: "application/json" })); } } catch (_) {}
      return settle(null);
    }
    if (flying) { again = true; return; }                 // one POST in flight: the next one carries what piled up
    flying = true;
    const b = body(false);
    Promise.resolve(post(url, { method: "POST", headers: { "Content-Type": "application/json" },
                                body: JSON.stringify(b), keepalive: true }))
      .then(async (r) => ({ status: r && r.status, out: r && r.json ? await r.json().catch(() => null) : null }))
      .catch(() => ({ status: 0, out: null }))
      .then(({ status, out }) => {
        flying = false;
        const ok = !status || (status >= 200 && status < 300);
        if (!ok || !out) full = true;                     // lost or refused: the next report says everything
        if (status === 409 && out && /replaced/.test(String(out.error || "")) && !retaken && !dead
            && (typeof document === "undefined" || document.visibilityState !== "hidden")) {
          retaken = true; mount = _newMount(); n = 0; full = true; again = true;   // the tab he looks at takes it back
        }
        settle(ok && out && Array.isArray(out.facts) ? out.facts : null);
        if (again && !dead) { again = false; send(false); }
      });
  };
  const schedule = () => { if (!timer && !dead) timer = setTimeout(() => send(false), COALESCE_MS); };

  const rep = {
    get mount() { return mount; },
    // The card's one door: what it shows now. `{applied: true}` = the last pushed revision is applied and settled;
    // `{forget: [names]}` = fields it can no longer vouch for. Resolves to the engine's facts for this screen.
    report(patch, o = {}) {
      if (dead) return Promise.resolve(null);
      let changed = false;
      for (const k of o.forget || []) { if (k in last) { delete last[k]; pending[k] = null; changed = true; } }
      for (const [k, v] of Object.entries(patch || {})) {
        if (v === undefined || v === null || last[k] === v) continue;
        last[k] = v; pending[k] = v; changed = true;
      }
      if (o.applied && seen) { ack = seen; full = true; changed = true; }
      if (!changed && !full) return Promise.resolve(lastFacts);
      const p = new Promise((res) => waiters.push(res));
      schedule();
      return p;
    },
    // The host: a data push carried revision `rev` ({epoch, rev}); the card has not applied it yet.
    seen(rev) { if (rev && rev.epoch && Number.isInteger(rev.rev)) seen = rev; },
    _snapshot(beacon, visibleAgain = false) {
      if (dead || !Object.keys(last).length) return;
      if (visibleAgain) retaken = false;
      full = true;
      if (beacon) send(true); else schedule();
    },
    dispose() { dead = true; clearTimeout(timer); _live.delete(rep); settle(null); },
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
