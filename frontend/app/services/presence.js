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
//   · on the engine's `engine.sleep` the WHOLE screen goes dark (`DormantVeil.js`, face "sleep") with a Reactivate
//     button; any gesture wakes it, and the veil shows that it is waiting until the stream answers;
//   · a hidden tab never reconnects, and becoming visible again is not a gesture.
// While asleep the tab sends nothing: pollers and voice retries ask `asleep()` before they reach the server.
// Every open this module decides carries `wake=1`: it is a person, and a deployment whose edge lets only a person
// start a stopped engine (a navigation or this mark) tells it apart from a stream the browser would retry on its own.
//
// PRESENCE IS CONNECTION (operator, 2026-11-10): a VISIBLE tab with its stream open is a person, even if he never
// speaks. It says so to the engine (`h.beat`, `POST /api/screens/beat {present}`) when the stream opens, when it
// becomes visible, and every `PRESENCE_BEAT_MS` — never while hidden or asleep — and the idle stop keeps the engine
// up for its whole window after the last one (`nucleo/idle_stop.py`).
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

/** Whether a presence beat is owed now: a visible tab, awake, with its stream open. Pure. */
export function beatDue({ visible, open, asleep }) {
  return !!(visible && open && !asleep);
}

// A page load is someone opening it: the first stream, and its retries while visible, are allowed for one window.
// `why` is what put the tab to sleep: "tab" (its own timer, a failed reconnect) or "engine" (`engine.sleep`).
const _p = { lastInput: Date.now(), asleep: false, why: "", waking: false, open: false, sleepMin: TAB_SLEEP_MIN,
             attempt: 0, timer: null, h: null, pill: null };

export const asleep = () => _p.asleep;

const _visible = () => { try { return !document.hidden; } catch (_) { return true; } };

function _beat() {
  if (!beatDue({ visible: _visible(), open: _p.open, asleep: _p.asleep })) return;
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
  const input = () => { _p.lastInput = Date.now(); if (_p.asleep) wake(); };
  for (const ev of ["pointerdown", "keydown"]) window.addEventListener(ev, input, { capture: true, passive: true });
  const iv = setInterval(() => { if (!_p.asleep && sleepDue({ lastInputMs: _p.lastInput, nowMs: Date.now(), sleepMin: _p.sleepMin })) sleep(); }, 30000);
  if (iv && iv.unref) iv.unref();   // a node harness that mounts sse.js must still exit; a browser returns a number
  const bv = setInterval(_beat, PRESENCE_BEAT_MS);
  if (bv && bv.unref) bv.unref();
  // Becoming visible is not a GESTURE (it never reopens a stream), but a visible tab whose stream is open is a person.
  try { document.addEventListener("visibilitychange", _beat); } catch (_) {}
}

/** What the stream itself says about presence: the hello's `tab_sleep_min`, `engine.sleep`, and his spoken turn. */
export function presenceEvent(d) {
  if (!d) return;
  if (d.kind === "session" && d.tab_sleep_min !== undefined && Number(d.tab_sleep_min) >= 0) _p.sleepMin = Number(d.tab_sleep_min);
  else if (d.kind === "session" && d.label === "engine.sleep") sleep("engine");
  else if (d.kind === "transcript" && d.role === "user") _p.lastInput = Date.now();
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
  _p.lastInput = Date.now();
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
