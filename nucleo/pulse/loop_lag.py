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

WHERE it was held is sampled, not guessed: a daemon thread watches the probe's heartbeat and, while the loop is late,
reads the loop thread's stack (`sys._current_frames`) a few times a second. The stall's event carries the stack seen
most often (`where`), so «held 19.5 s (its own work)» names the code that held it. It costs nothing while the loop
runs: the sampler only reads a stack once the heartbeat is overdue.
"""
from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
from collections import Counter, deque

from loguru import logger

try:
    import resource
except ImportError:  # not POSIX: no page-fault evidence
    resource = None

_PERIOD_S = 0.5
_DEFAULT_BOUND_S = 1.0
_OURS_CPU_SHARE = 0.5    # the loop thread ran at least half the stalled stretch → its own work held the loop
BODY = "body_loop"       # the shed source and the reading's name: the body's loop, never the audio path
_SAMPLE_EVERY_S = 0.25   # how often the sampler looks; it reads a stack only while the heartbeat is overdue
_WHERE_DEPTH = 6         # frames kept per sample, innermost last
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_state: dict = {"loops": set(), "last": 0.0, "worst": 0.0, "n": 0, "total_s": 0.0, "stalls": deque(maxlen=64),
                "last_stall": None,       # a state record
                "beat": 0.0, "loop_tid": None, "samples": Counter()}
_sampler_thread: threading.Thread | None = None


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
        where, seen = _where()
        _state["stalls"].append((mono, wall, lag_s, who))
        _state["last_stall"] = {"at": wall, "s": round(lag_s, 2), "whose": who, "where": where, "where_samples": seen}
        _say(lag_s, who)
    else:
        _state.setdefault("samples", Counter()).clear()
    _shed(lag_s)
    return stalled


def _shed(lag_s: float) -> None:
    try:
        from voice import lag
        lag.note(lag_s, lag.BODY)
    except Exception as e:  # noqa: BLE001 — the reading stands without the envelope
        logger.debug(f"loop_lag: lag reader not told: {e!r}")


def _say(lag_s: float, who: str = "host") -> None:
    last = _state.get("last_stall") or {}
    where, seen = last.get("where") or [], last.get("where_samples", 0)
    try:
        from voice.observer import emit
        emit("homeostasis", f"host stalled {lag_s:.1f} s — the engine's loop did not run" if who == "host" else
             f"the engine's loop was held {lag_s:.1f} s ({'its own work' if who == 'engine' else 'cause unknown'})",
             role="system", text=(" ← ".join(reversed(where)) if where else ""),
             extra={"cat": "health", "kind_diag": "loop_lag", "lag_s": round(lag_s, 2), "source": BODY,
                    "bound_s": bound_s(), "whose": who, "cause": {"host": "machine"}.get(who, who),
                    "where": where or [], "where_samples": seen})
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


def _frames(frame) -> tuple:
    """The innermost `_WHERE_DEPTH` frames of OUR code (the engine's files), innermost last, as «path:line fn»."""
    out = []
    while frame is not None:
        path = frame.f_code.co_filename
        if path.startswith(_ROOT) and os.sep + ".venv" + os.sep not in path and "site-packages" not in path:
            out.append(f"{os.path.relpath(path, _ROOT)}:{frame.f_lineno} {frame.f_code.co_name}")
            if len(out) >= _WHERE_DEPTH:
                break
        frame = frame.f_back
    return tuple(reversed(out))


def _sample_once(period_s: float) -> bool:
    """Read the loop thread's stack once IF its heartbeat is overdue. True when it sampled."""
    tid, beat = _state.get("loop_tid"), _state.get("beat", 0.0)
    if tid is None or not beat or time.monotonic() - beat < period_s + max(0.5, bound_s() / 2):
        return False
    frame = sys._current_frames().get(tid)
    sig = _frames(frame) if frame is not None else ()
    if sig:
        _state.setdefault("samples", Counter())[sig] += 1
    return True


def _sampler(period_s: float) -> None:
    while True:
        time.sleep(_SAMPLE_EVERY_S)
        try:
            _sample_once(period_s)
        except Exception as e:  # noqa: BLE001 — a sampler that fails never takes the body down
            logger.debug(f"loop_lag: sample failed: {e!r}")


def _where() -> tuple[list, int]:
    """The stack seen most often while the loop was held, and how many samples saw it; the samples are consumed."""
    got, _state["samples"] = _state.get("samples") or Counter(), Counter()
    if not got:
        return [], 0
    sig, n = got.most_common(1)[0]
    return list(sig), n


async def _probe(period_s: float = _PERIOD_S) -> None:
    loop = asyncio.get_running_loop()
    _state["loop_tid"] = threading.get_ident()
    while True:
        t0, c0, f0 = loop.time(), time.thread_time(), _major_faults()
        _state["beat"] = time.monotonic()
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
    global _sampler_thread
    if _sampler_thread is None:          # one per process, whatever loops it watches
        _sampler_thread = threading.Thread(target=_sampler, args=(_PERIOD_S,), name="body-loop-lag-sampler",
                                           daemon=True)
        _sampler_thread.start()
    return True


def give_way(i: int, every: int = 50, pace_s: float = 0.05, window_s: float = 5.0) -> bool:
    """Called by heavy work in a THREAD once per row: every `every` rows it yields the interpreter, and while the loop
    has stalled within `window_s` it also sleeps `pace_s`, so the host has room to run the loop. True when it paced."""
    if i % max(1, int(every)):
        return False
    paced = stalled_since(mono=time.monotonic() - window_s) > 0
    time.sleep(pace_s if paced else 0)
    return paced
