// ============================================================================
// screen-reporter.js — a screen says what it SHOWS, as ONE small document (V2-907 §3.1, §3.2).
//
// Both hosts (the desktop's windows and the phone's deck) build the same document from an ADAPTER they implement:
//   { layout: "windows"|"deck", list() → ids, vis(id) → front|visible|behind|min, layer(id) → 0 = on top,
//     home() → {shown, holds: [names]}, panel() → native surface open or "", flags(id) → {max, fs} (optional),
//     restoring() → true while the host is still bringing its saved apps back (optional, `watchRestore`) }
// and hand it to this module, which POSTs `{dev, mount, n, doc, acks, by}` to `/api/screen/report` — the one door
// of the screen's document on the engine (`widgets/screen_doc.write`). Nothing here knows a card.
//
//   · a MOUNT is one life of the host (a reload is a new mount); `n` goes forward within it; the first report of a
//     mount, a reopened event stream (`reportAll`), the tab coming back into view and `pagehide` (by beacon) send
//     the document whole even if nothing changed;
//   · a change (`changed(by)`) is coalesced for `DEBOUNCE_MS`; the same document twice is not said again;
//   · an ORDER's answer (`ack(seq, ok, why)`) is flushed AT ONCE, never debounced: the engine waits on it;
//   · while the host restores (a reload), the document says `unknown: true` — never the empty screen of that instant;
//   · one POST in flight; a lost or refused POST keeps its answers for the next one; a lost one (no answer, 429,
//     5xx) is tried again up to RETRIES times, each wait twice the last; a mount the engine says was
//     replaced takes the screen back with a new mount while the tab is in view.
// ============================================================================

export const DEBOUNCE_MS = 250;
//: The closed set of answers an order gets (V2-907 §3.2), each with whether the screen did it.
const WHY = { done: true, not_open: false, already_front: false, already_closed: false, elsewhere: false, refused: false };
const URL_ = "/api/screen/report";
const RETRIES = 3;
const _live = new Set();

const _hidden = () => typeof document !== "undefined" && document.visibilityState === "hidden";
if (typeof document !== "undefined" && document.addEventListener && !globalThis.__hbScreenReporterBound) {
  globalThis.__hbScreenReporterBound = true;
  document.addEventListener("visibilitychange", () => { for (const r of _live) r.snapshot(_hidden()); });
  globalThis.addEventListener && globalThis.addEventListener("pagehide", () => { for (const r of _live) r.snapshot(true); });
}

// The event stream reopened (a reconnect, an engine restart that forgot every screen): every host says it all again.
export function reportAll() { for (const r of _live) r.snapshot(false); }

// A POST the engine never answered, or answered as unable to take it now: the same report is tried again (backoff).
const _lost = (status) => status === 0 || status === 429 || status >= 500;
const _newMount = () => Math.random().toString(36).slice(2, 12);
//: A restore that never settles stops holding the screen unknown after this long: what it shows by then is the truth.
export const RESTORE_MAX_MS = 15000;

// The host's `restore()` (its saved apps coming back after a reload) is watched: `() => busy`, and `settled()` runs
// once it ends (or after RESTORE_MAX_MS). Wraps the instance's method, so the host's own code is unchanged.
export function watchRestore(host, settled) {
  let busy = false;
  const orig = host && typeof host.restore === "function" ? host.restore : null;
  if (!orig) return () => false;
  const done = () => { if (busy) { busy = false; settled(); } };
  host.restore = function (...a) {
    busy = true;
    const cap = setTimeout(done, RESTORE_MAX_MS);
    let p;
    try { p = orig.apply(this, a); } catch (e) { clearTimeout(cap); done(); throw e; }
    Promise.resolve(p).catch(() => {}).then(() => { clearTimeout(cap); done(); });
    return p;
  };
  return () => busy;
}

export function screenReporter(adapter, opts = {}) {
  const post = opts.fetch || ((u, init) => fetch(u, init));
  const beacon = opts.beacon || ((u, body) => typeof navigator !== "undefined" && navigator.sendBeacon
    && navigator.sendBeacon(u, new Blob([body], { type: "application/json" })));
  const deviceOf = typeof opts.device === "function" ? opts.device : async () => opts.device || "";
  let dev = typeof opts.device === "string" ? opts.device : "";
  let mount = _newMount(), n = 0, timer = null, flying = false, again = false, force = true, dead = false;
  let last = "", acks = [], by = "", fails = 0;

  const doc = () => {
    if (adapter.restoring && adapter.restoring()) return { layout: adapter.layout, unknown: true };
    const ids = [...(adapter.list() || [])];
    const open = ids.map((id, i) => {
      const layer = adapter.layer ? adapter.layer(id) : i;
      const row = { id, layer: Number.isInteger(layer) ? layer : i, vis: adapter.vis(id) || "behind" };
      const f = (adapter.flags && adapter.flags(id)) || {};
      if (f.max) row.max = true;
      if (f.fs) row.fs = true;
      return row;
    }).sort((a, b) => a.layer - b.layer);
    const front = (open.find((r) => r.vis === "front") || {}).id || "";
    const home = (adapter.home && adapter.home()) || {};
    return { layout: adapter.layout, front, open, panel: (adapter.panel && adapter.panel()) || "",
             home: { shown: home.shown === true, holds: Array.isArray(home.holds) ? home.holds : [] } };
  };
  const body = (d) => {
    n += 1;
    const out = { dev, mount, n, doc: d, acks, by };
    acks = []; by = "";
    return out;
  };

  const send = async (beaconNow = false) => {
    clearTimeout(timer); timer = null;
    if (dead) return;
    if (flying && !beaconNow) { again = true; return; }
    if (beaconNow) {
      try { beacon(URL_, JSON.stringify(body(doc()))); } catch (_) {}
      return;
    }
    flying = true;
    if (!dev) { try { dev = String((await deviceOf()) || ""); } catch (_) { dev = ""; } }
    const d = doc(), key = JSON.stringify(d);
    if (dead || (!force && !acks.length && key === last)) { flying = false; return; }   // nothing new to say
    force = false;
    const b = body(d);
    let status = 0;
    try {
      const r = await post(URL_, { method: "POST", headers: { "Content-Type": "application/json" },
                                   body: JSON.stringify(b), keepalive: true });
      status = (r && r.status) || 200;
    } catch (_) { status = 0; }
    flying = false;
    if (status >= 200 && status < 300) { last = key; fails = 0; }
    else {
      acks = b.acks.concat(acks); last = ""; force = true;  // a lost answer is said again, never dropped
      if (fails++ < RETRIES) {
        if (status === 409 && !_hidden()) { mount = _newMount(); n = 0; again = true; }   // replaced: take it back
        else if (acks.length || _lost(status)) timer = setTimeout(() => send(false), DEBOUNCE_MS * 4 * 2 ** (fails - 1));
      }
    }
    if (again && !dead) { again = false; send(false); }
  };
  const schedule = (ms = DEBOUNCE_MS) => { if (!timer && !dead) timer = setTimeout(() => send(false), ms); };

  const rep = {
    get mount() { return mount; },
    /** The host changed what it shows (`by` = his hand, the engine, code, a restore): said within DEBOUNCE_MS. */
    changed(cause = "") { if (cause) by = String(cause); schedule(); },
    /** The host ran order `seq`: its answer goes out NOW, with the document as it stands after it. */
    ack(seq, ok, why) {
      if (dead || !Number.isInteger(seq) || seq <= 0) return;
      let w = Object.prototype.hasOwnProperty.call(WHY, why) ? why : (ok ? "done" : "refused");
      if (w === "done" && !ok) w = "refused";                // «done» is the screen's word only when it did it
      acks.push({ seq, ok: WHY[w], why: w });
      send(false);
    },
    /** Say the whole document now (`beacon` = the page is going away). */
    snapshot(beaconNow = false) { if (dead) return; force = true; send(!!beaconNow); },
    dispose() { dead = true; clearTimeout(timer); _live.delete(rep); },
  };
  _live.add(rep);
  timer = setTimeout(() => send(false), 0);                  // the first report of a mount, whole
  return rep;
}
