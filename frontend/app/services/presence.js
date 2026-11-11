// ============================================================================
// presence.js — V2-872: presence is a connected PERSON, never a stream on its own.
//
// An engine with an idle stop ends (or is suspended) when nobody uses it, and any request can start it again. An open
// tab whose EventSource reconnects on its own after every stop starts the engine again and again, each boot spending
// the host's CPU with nobody there. So this tab never reconnects by itself:
//   · a stream error CLOSES the stream; reopening it is `reconnectDecision`'s call — only while the tab is visible
//     AND had input (pointer, key, his spoken turn) within `tab_sleep_min`, with a 2 s → 60 s backoff;
//   · a tab with no input for `tab_sleep_min` sleeps on its own (the orb dims, a line under it says so), and the
//     first gesture wakes it;
//   · on the engine's `engine.sleep` the WHOLE screen goes dark (`Veil.js`, face "sleep") with a Reactivate
//     button; any gesture wakes it, and the veil shows that it is waiting until the stream answers;
//   · a hidden tab never reconnects, and becoming visible again is not a gesture.
// While asleep the tab sends nothing: pollers and voice retries ask `asleep()` before they reach the server.
// Every open this module decides carries `wake=1`: it is a person, and a deployment whose edge lets only a person
// start a stopped engine (a navigation or this mark) tells it apart from a stream the browser would retry on its own.
//
// PRESENCE IS A GESTURE (operator, 2026-11-11 — replaces «presence is connection» of 2026-11-10): a tab that is
// merely VISIBLE is not a person. A tab that comes to the foreground, or that the browser itself reloads (a discarded
// tab restored, a session restore, a back/forward or prerender load), kept a hosted engine awake with nobody using
// it. So the beat (`h.beat`, `POST /api/screens/beat {present}`) goes out only while the tab is visible, awake, with
// its stream open AND had a GESTURE within `tab_sleep_min`: a pointer, a key, his spoken turn, or a page he opened
// himself (`openedByPerson`). Never while hidden or asleep. The idle stop keeps the engine up for its whole window
// after the last beat (`nucleo/idle_stop.py`).
//
// No imports on purpose: the decision is driven by a node test, and the shell hands in what it needs.
// ============================================================================

//: The policy key `tab_sleep_min` (config/resources.default.json); the stream's hello brings the deployment's value.
export const TAB_SLEEP_MIN = 10;
//: How often a visible, connected, awake tab tells the engine a person is there.
export const PRESENCE_BEAT_MS = 60000;
const BACKOFF_FIRST_MS = 2000, BACKOFF_CAP_MS = 60000;

/** Whether a closed stream may be reopened now, and after how long. Pure: everything comes in as arguments.
 *  `sleepMin` 0 turns the sleep off (input never goes stale); a hidden or sleeping tab never reconnects. */
export function reconnectDecision({ visible, lastInputMs, nowMs, asleep, attempt = 0, sleepMin = TAB_SLEEP_MIN }) {
  const recent = sleepMin <= 0 || (lastInputMs > 0 && nowMs - lastInputMs < sleepMin * 60000);
  if (asleep || !visible || !recent) return { reconnect: false, delayMs: 0 };
  return { reconnect: true, delayMs: Math.min(BACKOFF_CAP_MS, BACKOFF_FIRST_MS * 2 ** Math.max(0, attempt | 0)) };
}

/** Whether a tab with no input since `lastInputMs` should go to sleep now. */
export function sleepDue({ lastInputMs, nowMs, sleepMin = TAB_SLEEP_MIN }) {
  return sleepMin > 0 && nowMs - lastInputMs >= sleepMin * 60000;
}

/** Whether a presence beat is owed now: a visible tab, awake, with its stream open, touched by a person within
 *  `sleepMin` (0 = no idle stop: an open stream costs nothing, any visible tab may beat). Pure. */
export function beatDue({ visible, open, asleep, lastGestureMs = 0, nowMs = 0, sleepMin = TAB_SLEEP_MIN }) {
  const touched = sleepMin <= 0 || (lastGestureMs > 0 && nowMs - lastGestureMs < sleepMin * 60000);
  return !!(visible && open && !asleep && touched);
}

/** Whether this page load was a person opening it: a navigation or a reload he made — not a tab the browser
 *  restored on its own (`wasDiscarded`), a back/forward or a prerender. Pure: the shell hands in the document's
 *  `wasDiscarded` and the navigation entry's `type`. Unknown counts as a person (an old browser loses nothing). */
export function openedByPerson({ wasDiscarded = false, navType = "" } = {}) {
  if (wasDiscarded) return false;
  return !navType || navType === "navigate" || navType === "reload";
}

/** The server's ⏻ truth (`GET /api/run`), REFLECTED and never propagated: a tab that slept or sat hidden missed the
 *  `run` events, so it reads the switch again when it comes back. A reply asked before the operator's last command is
 *  history (main.js's boot probe has the same rule). `s` is the store's power API. Returns the state applied. */
export function reflectRunState(r, askedAt, s) {
  if (!r || typeof r.running !== "boolean" || !s) return null;
  if (s.powerCmdAt() > askedAt) return null;
  const off = !r.running;
  if (off !== s.powerOff()) s.setPowerOff(off);
  return off;
}

/** The tab came back (its stream reopened, or it became visible awake): read the ⏻ instead of trusting what it last
 *  heard. A background request: a hosted edge answers it without waking anything. */
export function syncRunState(s, fetchFn = globalThis.fetch) {
  if (_p.asleep) return;
  const askedAt = Date.now();
  fetchFn("/api/run", { cache: "no-store" }).then((r) => (r.ok ? r.json() : null))
    .then((r) => reflectRunState(r, askedAt, s)).catch(() => {});
}

function _navNow() {
  try {
    const n = performance.getEntriesByType("navigation")[0];
    return { wasDiscarded: !!document.wasDiscarded, navType: (n && n.type) || "" };
  } catch (_) { return {}; }
}

// A page load is someone opening it: the first stream, and its retries while visible, are allowed for one window.
// `why` is what put the tab to sleep: "tab" (its own timer, a failed reconnect) or "engine" (`engine.sleep`).
// `lastInput` keeps a just-loaded tab's stream (its retries, its own sleep timer); `lastGesture` is what a beat needs.
const _p = { lastInput: Date.now(), lastGesture: openedByPerson(_navNow()) ? Date.now() : 0, asleep: false, why: "", waking: false, open: false, sleepMin: TAB_SLEEP_MIN,
             attempt: 0, timer: null, h: null, pill: null };

export const asleep = () => _p.asleep;

const _visible = () => { try { return !document.hidden; } catch (_) { return true; } };

function _beat() {
  if (!beatDue({ visible: _visible(), open: _p.open, asleep: _p.asleep, lastGestureMs: _p.lastGesture,
                 nowMs: Date.now(), sleepMin: _p.sleepMin })) return;
  try { _p.h && _p.h.beat && _p.h.beat(); } catch (_) {}
}

// What the full-screen veil shows: "sleep" while the engine sleeps, `waking` once a gesture asked it back.
function _dormant() {
  try { _p.h && _p.h.dormant && _p.h.dormant({ face: _p.why === "engine" ? "sleep" : "", waking: _p.waking }); } catch (_) {}
}

/** Wired once by sse.js: `open()` / `close()` the stream, `t` names the dormant state. */
export function wirePresence(h) {
  if (_p.h) return;
  _p.h = h;
  // A hosted edge's «wake» button lands here with `?wake=1`: drop it, so a later restore of this address by the
  // browser is not read as a gesture again.
  try {
    const u = new URL(location.href);
    if (u.searchParams.has("wake")) { u.searchParams.delete("wake"); history.replaceState(history.state, "", u.pathname + u.search + u.hash); }
  } catch (_) {}
  const input = () => { _p.lastInput = _p.lastGesture = Date.now(); if (_p.asleep) wake(); };
  for (const ev of ["pointerdown", "keydown"]) window.addEventListener(ev, input, { capture: true, passive: true });
  const iv = setInterval(() => { if (!_p.asleep && sleepDue({ lastInputMs: _p.lastInput, nowMs: Date.now(), sleepMin: _p.sleepMin })) sleep(); }, 30000);
  if (iv && iv.unref) iv.unref();   // a node harness that mounts sse.js must still exit; a browser returns a number
  const bv = setInterval(_beat, PRESENCE_BEAT_MS);
  if (bv && bv.unref) bv.unref();
  // Becoming visible is not a GESTURE: it reopens nothing and beats only for a tab a person touched recently. It
  // does read the ⏻ again (`h.comeBack`, a background request a hosted edge answers without waking anything).
  try {
    document.addEventListener("visibilitychange", () => {
      _beat();
      if (_visible() && !_p.asleep) { try { _p.h && _p.h.comeBack && _p.h.comeBack(); } catch (_) {} }
    });
  } catch (_) {}
}

/** What the stream itself says about presence: the hello's `tab_sleep_min`, `engine.sleep`, and his spoken turn. */
export function presenceEvent(d) {
  if (!d) return;
  if (d.kind === "session" && d.tab_sleep_min !== undefined && Number(d.tab_sleep_min) >= 0) _p.sleepMin = Number(d.tab_sleep_min);
  else if (d.kind === "session" && d.label === "engine.sleep") sleep("engine");
  else if (d.kind === "transcript" && d.role === "user") _p.lastInput = _p.lastGesture = Date.now();
}

/** The stream answered: the engine is awake. The veil lifts, and a visible tab says a person is here. */
export function onStreamOpen() {
  _p.attempt = 0; _p.open = true;
  if (_p.why || _p.waking) { _p.why = ""; _p.waking = false; _dormant(); }
  _beat();
}

/** The stream failed and sse.js closed it: reconnect with backoff while he is here, otherwise sleep. */
export function onStreamError() {
  _p.open = false;
  if (_p.timer || _p.asleep) return;
  const now = () => ({ visible: !document.hidden, lastInputMs: _p.lastInput, nowMs: Date.now(), asleep: _p.asleep, sleepMin: _p.sleepMin });
  const d = reconnectDecision({ ...now(), attempt: _p.attempt });
  if (!d.reconnect) return sleep();
  _p.attempt++;
  _p.timer = setTimeout(() => {
    _p.timer = null;
    if (reconnectDecision(now()).reconnect) _p.h && _p.h.open({ wake: true }); else sleep();
  }, d.delayMs);
}

/** `why` "engine" is the engine's goodnight: the whole screen goes dark (the veil), not only the orb. A tab already
 *  asleep on its own timer that hears it keeps sleeping; a wake that gives up returns to the veil it came from. */
export function sleep(why = "tab") {
  if (why === "engine" || _p.waking) _p.why = "engine";
  _p.waking = false; _p.open = false;
  if (_p.asleep) { _dormant(); return; }
  _p.asleep = true;
  if (_p.timer) { clearTimeout(_p.timer); _p.timer = null; }
  try { _p.h && _p.h.close(); } catch (_) {}
  paint(true);
  _dormant();
}

function wake() {
  _p.asleep = false; _p.attempt = 0;
  if (_p.why === "engine") _p.waking = true;     // the veil stays, saying it is waiting, until the stream answers
  paint(false);
  _dormant();
  try { _p.h && _p.h.open({ wake: true }); } catch (_) {}
}

/** The veil's Reactivate: a gesture, like any other — it wakes the tab, and the tab's `wake=1` wakes the engine. */
export function reactivate() {
  _p.lastInput = _p.lastGesture = Date.now();
  if (_p.asleep) wake();
}

// The dormant state, on both shells: the orb (`#orb`, the same id on desktop and phone) dims and a line under it
// says what to do. Built here so neither shell grows a second copy.
function paint(on) {
  try {
    const orb = document.getElementById("orb");
    if (orb) orb.style.opacity = on ? "0.35" : "";
    if (!_p.pill) {
      _p.pill = document.createElement("div");
      _p.pill.setAttribute("role", "status");
      _p.pill.style.cssText = "position:fixed;left:50%;bottom:16px;transform:translateX(-50%);z-index:9999;padding:6px 14px;"
        + "border-radius:999px;background:rgba(10,12,20,.82);color:#e8ecff;font:13px/1.3 system-ui,sans-serif;pointer-events:none";
      document.body.appendChild(_p.pill);
    }
    const own = on && _p.why !== "engine";        // the engine's sleep has the full-screen veil; the pill is the tab's
    _p.pill.textContent = own && _p.h && _p.h.t ? _p.h.t("orb.asleep") : "";
    _p.pill.style.display = own ? "" : "none";
  } catch (_) {}
}
