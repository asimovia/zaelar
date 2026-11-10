// ============================================================================
// presence.js — V2-872: presence is the PERSON, never the tab.
//
// A hosted engine stops when nobody uses it, and any request starts it again. An open tab whose EventSource
// reconnected on its own after every stop booted one engine 35 times in 26 h, each boot burning the host's CPU
// quota with nobody there. So this tab never reconnects by itself:
//   · a stream error CLOSES the stream; reopening it is `reconnectDecision`'s call — only while the tab is visible
//     AND had input (pointer, key, his spoken turn) within `tab_sleep_min`, with a 2 s → 60 s backoff;
//   · a tab with no input for `tab_sleep_min` sleeps on its own, and so does every tab on the engine's
//     `engine.sleep`: the stream closes, the orb says so, and the first gesture wakes it;
//   · a hidden tab never reconnects, and becoming visible again is not a gesture.
// While asleep the tab sends nothing: pollers and voice retries ask `asleep()` before they reach the server.
//
// No imports on purpose: the decision is driven by a node test, and the shell hands in what it needs.
// ============================================================================

//: The policy key `tab_sleep_min` (config/resources.default.json); the stream's hello brings the deployment's value.
export const TAB_SLEEP_MIN = 10;
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

// A page load is someone opening it: the first stream, and its retries while visible, are allowed for one window.
const _p = { lastInput: Date.now(), asleep: false, sleepMin: TAB_SLEEP_MIN, attempt: 0, timer: null, h: null, pill: null };

export const asleep = () => _p.asleep;

/** Wired once by sse.js: `open()` / `close()` the stream, `t` names the dormant state. */
export function wirePresence(h) {
  if (_p.h) return;
  _p.h = h;
  const input = () => { _p.lastInput = Date.now(); if (_p.asleep) wake(); };
  for (const ev of ["pointerdown", "keydown"]) window.addEventListener(ev, input, { capture: true, passive: true });
  const iv = setInterval(() => { if (!_p.asleep && sleepDue({ lastInputMs: _p.lastInput, nowMs: Date.now(), sleepMin: _p.sleepMin })) sleep(); }, 30000);
  if (iv && iv.unref) iv.unref();   // a node harness that mounts sse.js must still exit; a browser returns a number
}

/** What the stream itself says about presence: the hello's `tab_sleep_min`, `engine.sleep`, and his spoken turn. */
export function presenceEvent(d) {
  if (!d) return;
  if (d.kind === "session" && d.tab_sleep_min !== undefined && Number(d.tab_sleep_min) >= 0) _p.sleepMin = Number(d.tab_sleep_min);
  else if (d.kind === "session" && d.label === "engine.sleep") sleep();
  else if (d.kind === "transcript" && d.role === "user") _p.lastInput = Date.now();
}

export function onStreamOpen() { _p.attempt = 0; }

/** The stream failed and sse.js closed it: reconnect with backoff while he is here, otherwise sleep. */
export function onStreamError() {
  if (_p.timer || _p.asleep) return;
  const now = () => ({ visible: !document.hidden, lastInputMs: _p.lastInput, nowMs: Date.now(), asleep: _p.asleep, sleepMin: _p.sleepMin });
  const d = reconnectDecision({ ...now(), attempt: _p.attempt });
  if (!d.reconnect) return sleep();
  _p.attempt++;
  _p.timer = setTimeout(() => {
    _p.timer = null;
    if (reconnectDecision(now()).reconnect) _p.h && _p.h.open(); else sleep();
  }, d.delayMs);
}

export function sleep() {
  if (_p.asleep) return;
  _p.asleep = true;
  if (_p.timer) { clearTimeout(_p.timer); _p.timer = null; }
  try { _p.h && _p.h.close(); } catch (_) {}
  paint(true);
}

function wake() {
  _p.asleep = false; _p.attempt = 0;
  paint(false);
  try { _p.h && _p.h.open(); } catch (_) {}
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
    _p.pill.textContent = on && _p.h && _p.h.t ? _p.h.t("orb.asleep") : "";
    _p.pill.style.display = on ? "" : "none";
  } catch (_) {}
}
