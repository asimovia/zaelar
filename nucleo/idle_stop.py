"""nucleo/idle_stop.py — an engine nobody is using ends its own process, cleanly.

A deployment that runs one engine per account and pays for it by the minute relies on its platform to stop an idle
one. The platform decides "idle" from network traffic, and a half-open connection (a laptop that went to sleep with a
tab open) can look like traffic for hours. The engine knows better: it keeps a clock of REAL activity
(`observability/identity.py` — voice, workers, memory, widgets; never the pulse or a heartbeat).

So, when enabled, the pulse asks `maybe_stop()` once per tick, and the engine asks its server to exit when ALL hold:
  * no real activity for `ZAELAR_IDLE_STOP_MIN` minutes (counted from the later of that and the process start);
  * no Brain Worker session is active;
  * the next scheduled notice is not due within that same window (a deployment that wakes engines for notices
    starts it again before the next one — `nucleo/pulse/wake.py`).

PRESENCE IS THE PERSON, NEVER THE TAB (V2-872). Real activity includes a screen's INPUT (`voice/screens.py`: a
touch, a typed line, a spoken turn) and never a stream open, a beat or a visibility change: an open tab that
reconnects its stream is a request, not a person. Until the first input after boot the window is the short
`wake_grace_min` (`config/resources.default.json`): an engine woken by a request that brought nobody stops again
in minutes instead of a full window — measured, a tab's reconnect after every stop booted one engine 35 times in
26 h. Workers and due notices keep their veto in both windows.

Before exiting, the engine says goodnight: `engine.sleep` goes out on every open stream, and the exit waits one
beat (`SLEEP_FLUSH_S`) so it is delivered; the client goes dormant on it and never reconnects without a gesture.

The exit is the server's own graceful shutdown (`request_exit`, set by `server/__main__.py`), never a signal to
itself: the process ends with status 0, which a platform with an on-failure restart policy reads as "stopped on
purpose" and leaves stopped until the next request starts it.

Off by default: with `ZAELAR_IDLE_STOP_MIN` unset or 0 nothing here ever runs — a self-hosted engine stays up.
"""
from __future__ import annotations

import asyncio
import os
import time

from loguru import logger

_STARTED_MS = round(time.time() * 1000)
_state = {"requested": False}
_exit_hook = {"fn": None}
#: How long the exit waits after `engine.sleep` is published, so the open streams carry it before they close.
SLEEP_FLUSH_S = 1.0
#: Fallbacks when the resources policy cannot be read (its keys `wake_grace_min` and `tab_sleep_min`).
_POLICY_FALLBACK = {"wake_grace_min": 3, "tab_sleep_min": 10}


def window_min() -> int:
    try:
        return max(0, int(os.getenv("ZAELAR_IDLE_STOP_MIN", "0") or 0))
    except ValueError:
        return 0


def _policy_min(key: str) -> float:
    """A minutes value declared in the resources policy (`nucleo/workers/envelope.policy`); never negative."""
    try:
        from nucleo.workers import envelope
        return max(0.0, float(envelope.policy().get(key, _POLICY_FALLBACK[key])))
    except Exception:  # noqa: BLE001 — an unreadable policy keeps the declared default
        return float(_POLICY_FALLBACK[key])


def wake_grace_min() -> float:
    return _policy_min("wake_grace_min")


def tab_sleep_min() -> float:
    """How long a visible tab with no input keeps its stream (the client reads it from the stream's hello)."""
    return _policy_min("tab_sleep_min")


def request_exit(fn) -> None:
    """Registered by the entrypoint: the callable that asks the server to shut down gracefully."""
    _exit_hook["fn"] = fn


def decide(now_ms: int, last_real_ms: int | None, started_ms: int, workers_active: bool,
           next_due_s: float | None, window_ms: int, *, last_input_ms: int | None = None,
           grace_ms: int = 0) -> str | None:
    """Why the engine should stop now, or None. Pure — the clock and every reading come in as arguments.

    `last_input_ms` is the last input of a person on any screen; nothing else is presence. Until one lands after
    `started_ms`, the window is `grace_ms` counted from the boot alone (`last_real_ms` is not read: a boot and a
    reconnecting tab move it with nobody there); after it, the full window from the latest activity of either kind."""
    if window_ms <= 0:
        return None
    present = last_input_ms is not None and last_input_ms >= started_ms
    if not present and 0 < grace_ms < window_ms:
        quiet_ms, win, what = now_ms - started_ms, grace_ms, "nobody present since boot"
    else:
        quiet_ms = now_ms - max(last_real_ms or 0, last_input_ms or 0, started_ms)
        win, what = window_ms, "no real activity"
    if quiet_ms < win:
        return None
    if workers_active:
        return None
    if next_due_s is not None and next_due_s * 1000 - now_ms < window_ms:
        return None
    return f"{what} for {quiet_ms // 60000} min, no worker running, no notice due within {window_ms // 60000} min"


def _readings() -> tuple[int | None, bool, float | None]:
    from observability import identity
    last = identity.last_real_activity_ms()
    try:
        from nucleo.dispatch import registry
        workers = registry.has_active()
    except Exception:  # noqa: BLE001 — unreadable counts as busy: never stop on a guess
        workers = True
    try:
        from nucleo.pulse import scheduler
        nxt = scheduler.next_due()
    except Exception:  # noqa: BLE001
        return last, workers, 0.0                      # unreadable schedule: treat a notice as imminent
    return last, workers, (float(nxt) if nxt else None)


def _last_input() -> int | None:
    """The last input of a person on any screen (`voice/screens.py`) — never a stream, a beat or visibility."""
    try:
        from voice import screens
        return screens.last_input_ms()
    except Exception as e:  # noqa: BLE001 — unreadable: nobody counted as present, the grace holds
        logger.warning(f"idle stop: screen input unreadable, nobody counted as present: {e!r}")
        return None


def maybe_stop(now: float | None = None) -> bool:
    """One pulse's check. True when it asked the server to exit (once per process)."""
    window = window_min() * 60_000
    if not window or _state["requested"] or _exit_hook["fn"] is None:
        return False
    now_ms = round((time.time() if now is None else now) * 1000)
    last, workers, nxt = _readings()
    why = decide(now_ms, last, _STARTED_MS, workers, nxt, window, last_input_ms=_last_input(),
                 grace_ms=round(wake_grace_min() * 60_000))
    if not why:
        return False
    _state["requested"] = True
    logger.info(f"idle stop: {why} — shutting down cleanly")
    _say_goodnight()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return _exit()
    loop.call_later(SLEEP_FLUSH_S, _exit)          # one beat for `engine.sleep` to reach the open streams
    return True


def _say_goodnight() -> None:
    """`engine.sleep` on every open stream: the client goes dormant and waits for a gesture instead of reconnecting
    (a reconnect is a request, and a request starts a stopped engine again)."""
    try:
        from voice.observer import emit
        emit("session", "engine.sleep")
    except Exception as e:  # noqa: BLE001 — a lost goodnight never keeps the engine up
        logger.warning(f"idle stop: engine.sleep not published: {e!r}")


def _exit() -> bool:
    try:
        _exit_hook["fn"]()
    except Exception as e:  # noqa: BLE001
        _state["requested"] = False
        logger.warning(f"idle stop: the exit request failed: {e!r}")
        return False
    return True


def _reset_for_tests() -> None:
    _state["requested"] = False
    _exit_hook["fn"] = None
