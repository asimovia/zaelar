"""nucleo/pulse/loop_lag.py — the body measures its own event loop and names the host that stopped it (V2-891, E0).

Measured on the operator's machine (2026-11-12): with the host out of memory the body's loop stopped in stretches of
12–31 s. Nothing in the body read it — the lag watcher runs where the voice runs (`voice/lag.watch`, in the voice
process since V2-891) — so the engine blamed what it could see: the model («turn STALLED», a relay to the stand-in),
the provider's queue («hidden reasoning or provider queue»), and the voice process found a body «unreachable».

One probe on the server loop (`watch`), the same shape as the voice's: a sleep that wakes late by more than
`loop_lag_s` (declared beside the envelope in `config/resources.default.json`) is a STALL. A stall is
  · recorded with its end (monotonic and wall clock), so a turn can ask «was the loop stopped while I waited?»
    (`stalled_since`) and a verdict can say «host stalled N s» instead of blaming a provider;
  · one `homeostasis` event («host stalled N s») — the fact, on the timeline, where the mis-attributions used to be;
  · a quiet shed through `voice/lag.note(…, BODY)`: the worker envelope holds new workers; no words are spoken,
    because a stopped loop is never the audio path;
  · pressure for the shed ladder (`shed_actuators.reading` → `loop_lag_s`), which descends with `cause=machine` when
    our processes are within their budgets — the host is short, not the engine.
`give_way` is the seam heavy work in a thread calls between batches: it yields the interpreter and, while the loop is
stalling, paces itself so the host has room to let the loop run.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque

from loguru import logger

_PERIOD_S = 0.5
_DEFAULT_BOUND_S = 1.0
BODY = "body_loop"       # the shed source and the reading's name: the body's loop, never the audio path
_state: dict = dict(loops=set(), last=0.0, worst=0.0, n=0, total_s=0.0, stalls=deque(maxlen=64),
                    last_stall=None)      # a state record, not a table (node 7.73)


def bound_s() -> float:
    from nucleo.workers import envelope
    return float(envelope.policy().get("loop_lag_s", _DEFAULT_BOUND_S))


def note(lag_s: float, *, mono: float | None = None, wall: float | None = None) -> bool:
    """One reading of how late the loop woke. True when it was a stall (≥ `loop_lag_s`): recorded, said once as a
    `homeostasis` event, and shed quietly through the lag reader; under the bound the reader releases its hold."""
    lag_s = float(lag_s)
    _state["last"] = lag_s
    _state["worst"] = max(_state["worst"], lag_s)
    stalled = lag_s >= bound_s()
    if stalled:
        mono = time.monotonic() if mono is None else mono
        wall = time.time() if wall is None else wall
        _state["n"] += 1
        _state["total_s"] += lag_s
        _state["stalls"].append((mono, wall, lag_s))
        _state["last_stall"] = {"at": wall, "s": round(lag_s, 2)}
        _say(lag_s)
    _shed(lag_s)
    return stalled


def _shed(lag_s: float) -> None:
    try:
        from voice import lag
        lag.note(lag_s, lag.BODY)
    except Exception as e:  # noqa: BLE001 — the reading stands without the envelope
        logger.debug(f"loop_lag: lag reader not told: {e!r}")


def _say(lag_s: float) -> None:
    try:
        from voice.observer import emit
        emit("homeostasis", f"host stalled {lag_s:.1f} s — the engine's loop did not run", role="system",
             extra={"cat": "health", "kind_diag": "loop_lag", "lag_s": round(lag_s, 2), "source": BODY,
                    "bound_s": bound_s()})
    except Exception as e:  # noqa: BLE001 — a stall that cannot be said is still recorded
        logger.debug(f"loop_lag: event not emitted: {e!r}")


def stalled_since(mono: float | None = None, wall: float | None = None) -> float:
    """Seconds the loop was stopped by the stalls that ENDED after `mono` (monotonic) or `wall` — a wait that began
    during a stall could not begin, so a stall that ends inside the window counts whole. Both None: every stall kept."""
    total = 0.0
    for m, w, s in list(_state["stalls"]):
        if (mono is None or m > mono) and (wall is None or w > wall):
            total += s
    return round(total, 3)


def stalled_recently(window_s: float = 60.0, now: float | None = None) -> float:
    """Seconds of stall in the last `window_s` — the ladder's and the provider circuit's question."""
    now = time.monotonic() if now is None else now
    return stalled_since(mono=now - float(window_s))


def status() -> dict:
    """`GET /api/debug/loop`: the last reading, the worst, the last stall and how much was lost to stalls."""
    return {"last_lag_s": round(_state["last"], 3), "worst_lag_s": round(_state["worst"], 3), "stalls": _state["n"],
            "stalled_total_s": round(_state["total_s"], 2), "last_stall": _state["last_stall"],
            "stalled_last_60s": stalled_recently(60.0), "bound_s": bound_s(), "watching": bool(_state["loops"])}


async def _probe(period_s: float = _PERIOD_S) -> None:
    loop = asyncio.get_running_loop()
    while True:
        t0 = loop.time()
        await asyncio.sleep(period_s)
        note(max(0.0, loop.time() - t0 - period_s))


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
    paced = stalled_recently(window_s) > 0
    time.sleep(pace_s if paced else 0)
    return paced
