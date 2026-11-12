"""nucleo/pulse/loop_lag.py — the body measures its own event loop and names the host that stopped it (V2-891, E0).

Measured (2026-11-12): with the host out of memory the body's loop stopped 12–31 s and nothing in the body read it
(the lag watcher runs in the voice process since V2-891), so the engine blamed the model («turn STALLED», a relay to
the stand-in), the provider's queue, and the voice process found a body «unreachable».

One probe on the server loop (`watch`): a sleep that wakes later than `loop_lag_s` (beside the envelope) is a STALL —
recorded with its span (`stalled_since`: «was the loop stopped while I waited?»), one `homeostasis` event, a quiet
shed through `voice/lag.note(…, BODY)` (never words: not the audio path), and ladder pressure beat after beat.
WHOSE it was is measured (E3), never assumed: the LOOP THREAD's CPU over it — `engine` when it ran; `host` only when
the process paged (major faults grew); else `unknown` (a syscall, the GIL, descheduled).
`give_way` is the seam heavy work in a thread calls between batches: it yields, and paces itself while the loop stalls.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque

from loguru import logger

try:
    import resource
except ImportError:  # not POSIX: no page-fault evidence
    resource = None

_PERIOD_S = 0.5
_DEFAULT_BOUND_S = 1.0
_OURS_CPU_SHARE = 0.5    # the loop thread ran at least half the stalled stretch → its own work held the loop
BODY = "body_loop"       # the shed source and the reading's name: the body's loop, never the audio path
_state: dict = {"loops": set(), "last": 0.0, "worst": 0.0, "n": 0, "total_s": 0.0, "stalls": deque(maxlen=64),
                "last_stall": None}       # a state record


def bound_s() -> float:
    from nucleo.workers import envelope
    return float(envelope.policy().get("loop_lag_s", _DEFAULT_BOUND_S))


def note(lag_s: float, *, cpu_s=None, faults: int = 0, mono=None, wall=None) -> bool:
    """One reading of how late the loop woke (`cpu_s`: the loop thread's CPU over it, `faults`: major page faults).
    True when a stall (≥ `loop_lag_s`): recorded with whose it was, said once, shed quietly; else the hold ends."""
    lag_s = float(lag_s)
    _state["last"] = lag_s
    _state["worst"] = max(_state["worst"], lag_s)
    stalled = lag_s >= bound_s()
    if stalled:
        mono, wall = (time.monotonic() if mono is None else mono), (time.time() if wall is None else wall)
        _state.update(n=_state["n"] + 1, total_s=_state["total_s"] + lag_s)
        who = "engine" if (cpu_s or 0) >= _OURS_CPU_SHARE * lag_s else ("host" if faults > 0 else "unknown")
        _state["stalls"].append((mono, wall, lag_s, who))
        _state["last_stall"] = {"at": wall, "s": round(lag_s, 2), "whose": who}
        _say(lag_s, who)
    _shed(lag_s)
    return stalled


def _shed(lag_s: float) -> None:
    try:
        from voice import lag
        lag.note(lag_s, lag.BODY)
    except Exception as e:  # noqa: BLE001 — the reading stands without the envelope
        logger.debug(f"loop_lag: lag reader not told: {e!r}")


def _say(lag_s: float, who: str = "host") -> None:
    try:
        from voice.observer import emit
        emit("homeostasis", f"host stalled {lag_s:.1f} s — the engine's loop did not run" if who == "host" else
             f"the engine's loop was held {lag_s:.1f} s ({'its own work' if who == 'engine' else 'cause unknown'})",
             role="system",
             extra={"cat": "health", "kind_diag": "loop_lag", "lag_s": round(lag_s, 2), "source": BODY,
                    "bound_s": bound_s(), "whose": who, "cause": {"host": "machine"}.get(who, who)})
    except Exception as e:  # noqa: BLE001 — a stall that cannot be said is still recorded
        logger.debug(f"loop_lag: event not emitted: {e!r}")


def stalled_since(mono: float | None = None, wall: float | None = None, who: str | None = None) -> float:
    """Seconds the loop was stopped INSIDE the window opening at `mono` / `wall`: a stall counts only its overlap (E3
    audit: a block that ended just as a wait began was handed back whole). `who` keeps one origin."""
    def inside(end: float, since, s: float) -> float:
        return s if since is None else max(0.0, min(s, end - since))
    return round(sum(min(inside(m, mono, s), inside(w, wall, s)) for m, w, s, o in list(_state["stalls"])
                     if who is None or o == who), 3)


def status() -> dict:
    """`GET /api/debug/loop`: the last reading, the worst, the last stall and how much was lost to stalls."""
    return {"last_lag_s": round(_state["last"], 3), "worst_lag_s": round(_state["worst"], 3), "stalls": _state["n"],
            "stalled_total_s": round(_state["total_s"], 2), "last_stall": _state["last_stall"],
            "stalled_last_60s": stalled_since(mono=time.monotonic() - 60.0), "bound_s": bound_s(),
            "watching": bool(_state["loops"])}


async def _probe(period_s: float = _PERIOD_S) -> None:
    loop = asyncio.get_running_loop()
    while True:
        t0, c0, f0 = loop.time(), time.thread_time(), _major_faults()
        await asyncio.sleep(period_s)
        note(max(0.0, loop.time() - t0 - period_s), cpu_s=time.thread_time() - c0, faults=_major_faults() - f0)


def _major_faults() -> int:
    """The loop thread's major page faults (Linux; macOS: the process's, not its compressor: residual); 0 off POSIX."""
    return resource.getrusage(getattr(resource, "RUSAGE_THREAD", resource.RUSAGE_SELF)).ru_majflt if resource else 0


def watch() -> bool:
    """Measure the CURRENT event loop (the server's) for as long as it runs. Idempotent per loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError as e:
        logger.debug(f"loop_lag: no running loop to measure ({e})")
        return False
    if id(loop) in _state["loops"]:
        return False
    _state["loops"].add(id(loop))
    loop.create_task(_probe(), name="body-loop-lag-probe")
    return True


def give_way(i: int, every: int = 50, pace_s: float = 0.05, window_s: float = 5.0) -> bool:
    """Called by heavy work in a THREAD once per row: every `every` rows it yields the interpreter, and while the loop
    has stalled within `window_s` it also sleeps `pace_s`, so the host has room to run the loop. True when it paced."""
    if i % max(1, int(every)):
        return False
    paced = stalled_since(mono=time.monotonic() - window_s) > 0
    time.sleep(pace_s if paced else 0)
    return paced
