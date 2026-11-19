"""memory/lock_watch.py — the database lock names who held it when somebody waited (INI-042 #34).

`zaelar.db` is one connection behind one re-entrant lock (`memory/db.py`). A reader that waits on it waits for whoever
holds it, and until now nothing said who that was: the loop's stall sampler saw only the waiter («held 7.1 s at
`state.read`»). This lock keeps the holder's thread and, when an acquire has waited `SLOW_S`, reads that thread's
stack ONCE; when a hold itself lasts `SLOW_S` it keeps the releasing stack. Both are said after the lock is released
(a `homeostasis` event, `kind_diag=db_lock`) and kept for `GET /api/debug/loop`. An acquire that does not wait costs
one timed `acquire` and two attribute writes.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from collections import deque

from loguru import logger

SLOW_S = float(os.getenv("ZAELAR_DB_LOCK_SLOW_S", "0.5"))
_DEPTH = 8
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_state: dict = dict(waits=0, holds=0, worst_wait_s=0.0, worst_hold_s=0.0, recent=deque(maxlen=20))
_telling = threading.local()


def _stack(frame) -> list:
    """The frame's stack, innermost first: the innermost frame whatever it is (the call it is parked in), then the
    engine's own frames up to `_DEPTH`."""
    out, first = [], True
    while frame is not None and len(out) < _DEPTH:
        path = frame.f_code.co_filename
        if path == __file__:                   # the lock's own frames say nothing
            frame = frame.f_back
            continue
        ours = path.startswith(_ROOT) and "site-packages" not in path and os.sep + ".venv" + os.sep not in path
        if ours or first:
            where = os.path.relpath(path, _ROOT) if ours else os.path.basename(path)
            out.append(f"{where}:{frame.f_lineno} {frame.f_code.co_name}")
        first = False
        frame = frame.f_back
    return out


def _thread_name(tid) -> str:
    return next((t.name for t in threading.enumerate() if t.ident == tid), str(tid))


def status() -> dict:
    return {**_state, "recent": list(_state["recent"])}


def _tell(what: str, s: float, holder: str, stack: list, waiter: str = "") -> None:
    """Record one slow wait or hold and say it once. Never from inside itself: saying it reaches the database."""
    key = "waits" if what == "wait" else "holds"
    worst = "worst_wait_s" if what == "wait" else "worst_hold_s"
    _state[key] += 1
    _state[worst] = max(_state[worst], round(s, 3))
    _state["recent"].append({"what": what, "s": round(s, 3), "holder": holder, "stack": stack, "waiter": waiter,
                             "at": time.time()})
    if getattr(_telling, "on", False):
        return
    _telling.on = True
    try:
        from voice.observer import emit
        emit("homeostasis",
             (f"the database lock was waited on {s:.1f} s by {waiter} — held by {holder}" if what == "wait"
              else f"the database lock was held {s:.1f} s by {holder}"),
             role="system", text=" ← ".join(stack),
             extra={"cat": "health", "kind_diag": "db_lock", "what": what, "s": round(s, 3), "holder": holder,
                    "waiter": waiter, "where": stack})
    except Exception as e:  # noqa: BLE001 — a wait that cannot be said is still recorded
        logger.debug(f"lock_watch: event not emitted: {e!r}")
    finally:
        _telling.on = False


class WatchedLock:
    """A re-entrant lock that knows its holder. Same `with` / `acquire` / `release` as `threading.RLock`."""

    def __init__(self):
        self._lock = threading.RLock()
        self._owner: int | None = None
        self._depth = 0
        self._since = 0.0
        self._waited: tuple | None = None      # read and written only by the holder

    def held_by_me(self) -> bool:
        return self._owner == threading.get_ident()

    def acquire(self) -> bool:
        me = threading.get_ident()
        if self._owner == me:                  # re-entrant: nothing to wait for
            self._lock.acquire()
            self._depth += 1
            return True
        waited = None
        if not self._lock.acquire(timeout=SLOW_S):
            t0 = time.monotonic() - SLOW_S
            holder = self._owner
            frame = sys._current_frames().get(holder) if holder is not None else None
            seen = (_thread_name(holder), _stack(frame) if frame is not None else [])
            self._lock.acquire()
            waited = (time.monotonic() - t0, *seen)
        self._owner, self._depth, self._since, self._waited = me, 1, time.monotonic(), waited
        return True

    def release(self) -> None:
        self._depth -= 1
        if self._depth > 0:
            self._lock.release()
            return
        held, waited = time.monotonic() - self._since, self._waited
        self._owner, self._waited = None, None
        self._lock.release()
        me = threading.current_thread().name
        if waited is not None:
            _tell("wait", waited[0], waited[1], waited[2], waiter=me)
        if held >= SLOW_S:
            _tell("hold", held, me, _stack(sys._getframe(1)))

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()
        return False
