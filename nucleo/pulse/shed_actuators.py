"""nucleo/pulse/shed_actuators.py — the body's hands for each rung of the shed ladder (V2-891).

`nucleo/pulse/shed_ladder.py` is pure: it reads a reading and names one rung to engage or release. This module takes
the reading from the host (free memory against the deployment's floor, our own processes against their budgets) and
moves the rung it names. Every actuator is reversible or harmless, and none raises: a rung that cannot move says so in
the event and the ladder goes on.
"""
from __future__ import annotations

import asyncio
import gc
import sys
import time

from loguru import logger

from nucleo.pulse import loop_lag

_L: dict = {"ladder": None, "beat_at": None, "beat_lag": None}   # the previous beat: when, and its stalls


def ladder():
    if _L["ladder"] is None:
        from nucleo.pulse import shed_ladder
        from nucleo.workers import envelope
        _L["ladder"] = shed_ladder.from_policy(envelope.policy())
    return _L["ladder"]


def _rss_mb(pid: int | None = None) -> float:
    try:
        import psutil
        return psutil.Process(pid).memory_info().rss / 2 ** 20 if pid else psutil.Process().memory_info().rss / 2 ** 20
    except Exception as _swallowed:  # noqa: BLE001
        logger.debug(f"{__name__}: {_swallowed!r}")   # said, never silent (the ratchet)
        return 0.0


def _loop_beat() -> dict:
    """The loop's stalls since the last beat by origin: pressure reads the PERSISTING one (the lesser of this beat's and
    the last: a lone hiccup is the envelope's hold, E3), recovery THIS beat's (E3 audit)."""
    now, since, prev = time.monotonic(), _L["beat_at"], _L["beat_lag"]
    by = {who: loop_lag.stalled_since(mono=since, who=who) for who in ("host", "engine", "unknown")}
    beat = sum(by.values())
    _L["beat_at"], _L["beat_lag"] = now, beat
    return {"loop_lag_s": min(prev, beat) if prev is not None else 0.0, "loop_lag_now_s": beat, **by}


def reading() -> dict:
    """The host now: free memory, the floor, whose memory it is (`cause`), and the body loop's persisting stalls."""
    from nucleo.pulse import budgets, shed_ladder
    from nucleo.workers import envelope
    (total, avail), pol = envelope.measured(), envelope.policy()
    engine = _rss_mb()
    budget = budgets.budget("body", pol)["mb"]
    try:
        from voice import child_process
        child = child_process.current()
        if child is not None and not child_process.embedded():
            engine += child.rss_mb()
            budget += budgets.budget("voice", pol)["mb"]
    except Exception as _swallowed:  # noqa: BLE001
        logger.debug(f"{__name__}: {_swallowed!r}")   # said, never silent (the ratchet)
    beat = _loop_beat()                     # E0: the body's own loop stalls, named by whose they were (E3)
    return {"free_mb": avail / 2 ** 20, "floor_mb": envelope.floor(total, pol) / 2 ** 20,
            "engine_mb": round(engine, 1), "budget_mb": budget, "lag_bound_s": loop_lag.bound_s(),
            "cause": shed_ladder.cause(engine, budget, beat["engine"], beat["host"], beat["unknown"],
                                       avail < envelope.floor(total, pol)),
            "loop_lag_s": beat["loop_lag_s"], "loop_lag_now_s": beat["loop_lag_now_s"]}


def _workers():
    try:
        from nucleo import dispatch
        return list(dispatch._SESSIONS.values())
    except Exception as _swallowed:  # noqa: BLE001
        logger.debug(f"{__name__}: {_swallowed!r}")   # said, never silent (the ratchet)
        return []


def _engage(rung: str) -> str:
    from nucleo.workers import envelope
    if rung == "hold_workers":
        envelope.shed(3600.0, "ladder")         # its own source: released by THIS ladder only (V2-867)
        return "held"
    if rung == "pause_newest_worker":
        return envelope.relieve(_workers()) or "nothing to pause"
    if rung == "pause_background":
        from widgets import background
        background.hold(True)
        return "background ticks held"
    if rung == "close_browser":
        from search import browser
        ctx = getattr(browser, "_ctx", None)
        if ctx is None:
            return "no browser open"
        if getattr(ctx, "pages", None):
            return "browser in use — kept"
        asyncio.get_running_loop().create_task(browser.stop())
        return "idle browser closed"
    if rung == "trim_caches":
        freed = gc.collect()
        trimmed = False
        if sys.platform.startswith("linux"):
            try:
                import ctypes
                trimmed = bool(ctypes.CDLL("libc.so.6").malloc_trim(0))
            except Exception:  # noqa: BLE001
                trimmed = False
        return f"gc {freed} objects" + (", pages returned" if trimmed else "")
    return "unknown rung"


def _release(rung: str) -> str:
    from nucleo.workers import envelope
    if rung == "hold_workers":
        envelope.unshed("ladder")
        return "released"
    if rung == "pause_newest_worker":
        out = []
        for r in _workers():
            if getattr(r, "paused_by", "") == "envelope" and r.session.resume():
                r.paused_by = ""
                out.append(str(getattr(r, "task_id", "?")))
        return ("resumed " + ", ".join(out)) if out else "nothing paused"
    if rung == "pause_background":
        from widgets import background
        background.hold(False)
        return "background ticks resumed"
    return "nothing to undo"                    # a closed browser starts again on its next search; a gc is spent


def step(emit=None) -> dict | None:
    """One beat of the ladder: read, decide, move, say."""
    try:
        r = reading()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"shed ladder: no reading ({e!r})")
        return None
    if (act := ladder().step(r)) is None:
        return None
    try:
        did = _engage(act["engage"]) if "engage" in act else _release(act["release"])
    except Exception as e:  # noqa: BLE001 — a rung that cannot move says so; the ladder goes on
        did = f"failed: {e!r}"[:160]
    act = {**act, "did": did, "free_mb": round(r["free_mb"]), "floor_mb": round(r["floor_mb"]),
           "engine_mb": r["engine_mb"], "budget_mb": r["budget_mb"], "cause": r["cause"]}
    if emit is not None:
        rung = act.get("engage") or act.get("release")
        emit("shed_ladder", f"{'↓' if 'engage' in act else '↑'} {rung} — {did}",
             extra={"cat": "health", "kind_diag": "shed_ladder", **act})
    return act
