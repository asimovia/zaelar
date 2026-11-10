"""nucleo/idle_stop.py — an engine nobody is using goes to sleep, or ends its own process, cleanly.

A deployment that runs one engine per account and pays for it by the minute relies on its platform to stop an idle
one. The platform decides "idle" from network traffic, and a half-open connection (a laptop that went to sleep with a
tab open) can look like traffic for hours. The engine knows better: it keeps a clock of REAL activity
(`observability/identity.py` — voice, workers, memory, widgets; never the pulse, a heartbeat or a widget's own
background tick) and a clock of PRESENCE (`voice/screens.py`).

So, when enabled, the pulse asks `maybe_stop()` once per tick, and the engine stops when ALL hold:
  * no real activity and nobody present for `ZAELAR_IDLE_STOP_MIN` minutes (counted from the later of those and the
    process start — or the last resume);
  * no Brain Worker session is active;
  * the next scheduled notice the engine can still fire is not due within that same window (a deployment that wakes
    engines for notices starts it again before it — `nucleo/pulse/wake.py`). A job already past due when the pulse
    reaches this check is one this tick could not fire (⏻ off and no device to push to, or work that waits for ⏻):
    it waits for a person, not for the clock, so it vetoes nothing (`nucleo/pulse/due.py::next_owed`).

PRESENCE IS A CONNECTED PERSON. A screen's input (a touch, a typed line, a spoken turn) is presence, and so is a
VISIBLE tab whose stream is open: it says so with a beat every minute (`frontend/app/services/presence.js`), which
the server records as `screens.present()`. A stream open alone never is — a reconnecting tab is a request, not a
person — and a tab with no input for `tab_sleep_min` stops beating and closes its stream. Until someone is present
after boot (or after a resume) the window is the short `wake_grace_min`: an engine woken by a request that brought
nobody stops again in about a minute instead of a full window. Workers and due notices keep their veto in both.

HOW IT STOPS, AND THE RESUME. Once this decides, `nucleo/suspend.py` carries the stop out: the wake report first,
the goodnight on every open stream, then the deployment's sleep endpoint (suspend this host) or the server's own clean
exit; and on every beat it reads the clocks for a resume, after which the idle state counts from that instant.

Off by default: with `ZAELAR_IDLE_STOP_MIN` unset or 0 nothing here ever runs — a self-hosted engine stays up.
"""
from __future__ import annotations

import os
import time

from loguru import logger

from nucleo import suspend

_STARTED_MS = round(time.time() * 1000)
#: Fallbacks when the resources policy cannot be read (its keys `wake_grace_min` and `tab_sleep_min`).
_POLICY_FALLBACK = {"wake_grace_min": 1, "tab_sleep_min": 10}


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
    """The window for an engine nobody has come to since boot or resume. `ZAELAR_WAKE_GRACE_MIN` overrides the
    policy for one deployment; the policy's value is the default."""
    raw = (os.getenv("ZAELAR_WAKE_GRACE_MIN") or "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            logger.warning(f"idle stop: ZAELAR_WAKE_GRACE_MIN={raw!r} is not a number — the policy's value holds")
    return _policy_min("wake_grace_min")


def tab_sleep_min() -> float:
    """How long a visible tab with no input keeps its stream (the client reads it from the stream's hello). An engine
    that never stops (no idle stop: a self-hosted laptop) never puts a tab to sleep — an open stream costs it nothing,
    and a wall display is read without being touched — so it tells the tab 0."""
    return _policy_min("tab_sleep_min") if window_min() > 0 else 0.0


def decide(now_ms: int, last_real_ms: int | None, started_ms: int, workers_active: bool,
           next_due_s: float | None, window_ms: int, *, last_presence_ms: int | None = None,
           grace_ms: int = 0) -> str | None:
    """Why the engine should stop now, or None. Pure — the clock and every reading come in as arguments.

    `last_presence_ms` is the last moment a person was present (input, or a visible connected screen's beat); nothing
    else is presence. Until one lands after `started_ms` (the boot or the last resume), the window is `grace_ms`
    counted from that start alone (`last_real_ms` is not read: a boot moves it with nobody there); after it, the full
    window from the latest activity of either kind."""
    if window_ms <= 0:
        return None
    present = last_presence_ms is not None and last_presence_ms >= started_ms
    if not present and 0 < grace_ms < window_ms:
        quiet_ms, win, what = now_ms - started_ms, grace_ms, "nobody present since boot or resume"
    else:
        quiet_ms = now_ms - max(last_real_ms or 0, last_presence_ms or 0, started_ms)
        win, what = window_ms, "no real activity and nobody present"
    if quiet_ms < win:
        return None
    if workers_active:
        return None
    if next_due_s is not None and next_due_s * 1000 - now_ms < window_ms:
        return None
    return f"{what} for {quiet_ms // 60000} min, no worker running, no notice due within {window_ms // 60000} min"


def note_tick(wall: float | None = None, mono: float | None = None, tick_s: float = 1.0) -> bool:
    """The pulse's first call on every beat: True when the process was suspended and has just resumed
    (`suspend.note_tick`; it only looks while the idle stop is on)."""
    return suspend.note_tick(wall, mono, tick_s, enabled=bool(window_min()))


def _since_ms() -> int:
    return suspend.resumed_at_ms() or _STARTED_MS


def _readings(now: float) -> tuple[int | None, bool, float | None]:
    from observability import identity
    last = identity.last_real_activity_ms()
    try:
        from nucleo.dispatch import registry
        workers = registry.has_active()
    except Exception:  # noqa: BLE001 — unreadable counts as busy: never stop on a guess
        workers = True
    try:
        from nucleo.pulse import due
        nxt = due.next_owed(now)
    except Exception:  # noqa: BLE001
        return last, workers, 0.0                      # unreadable schedule: treat a notice as imminent
    return last, workers, nxt


def _last_presence() -> int | None:
    """The last moment a person was present on any screen (`voice/screens.py`) — input or a visible connected beat."""
    try:
        from voice import screens
        return screens.last_presence_ms()
    except Exception as e:  # noqa: BLE001 — unreadable: nobody counted as present, the grace holds
        logger.warning(f"idle stop: screen presence unreadable, nobody counted as present: {e!r}")
        return None


def maybe_stop(now: float | None = None) -> bool:
    """One pulse's check, called after `note_tick`. True when it started a stop, or carried one out."""
    window = window_min() * 60_000
    if not window or not suspend.can_exit():
        return False
    under_way = suspend.step()                          # a sleep already asked for decides this beat on its own
    if under_way is not None:
        return under_way
    now = time.time() if now is None else now
    now_ms = round(now * 1000)
    last, workers, nxt = _readings(now)
    why = decide(now_ms, last, _since_ms(), workers, nxt, window, last_presence_ms=_last_presence(),
                 grace_ms=round(wake_grace_min() * 60_000))
    return suspend.begin(why) if why else False
