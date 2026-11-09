"""nucleo/workers/envelope.py — background work can never starve the voice (V2-831 T-27).

On a small host with no swap, free memory can fall to zero over one voice session while errands run, and not come
back when they end; the VAD then falls behind real time («slower than realtime», «job executor unresponsive») and the
host freezes. The voice and the workers share the host, so the boundary between them has to be declared.

The boundary, as mechanism and data (`config/resources.default.json`, every number a RATIO of what the host measures):
  · a worker process tree runs at a LOWER scheduling priority (`preexec`);
  · a new worker is ADMITTED only while measured free memory is above the floor (`admits`, `wait_for_room`) — the
    LARGER of a ratio and an absolute reserve for the voice (`floor`, V2-867 T593) — and one at a time: the next is
    measured only once the previous one RUNS (`admitted`/`settled`), so on a tight host work runs one → one → one;
  · the wait has no clock (V2-867 T592): it lasts until there is room, and the operator's cancel is its exit; it says
    its TRUE reason (`reason`): the memory floor, the voice's shed, or the worker ahead still starting;
  · a shed names its source and ends when that source recovers (`unshed`), its seconds only a ceiling (T591);
  · above the ceiling of pressure the NEWEST running worker is paused, and resumed when there is room again
    (`relieve`), the same reversible pause the ⏻ uses;
  · its process GROUP is reaped when the errand ends (the providers' `stop`), so nothing it spawned outlives it.
"""
from __future__ import annotations

import asyncio
import json
import os
import time

from loguru import logger

_HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config")
_DEFAULTS = {"worker_nice": 10, "admit_free_ratio": 0.2, "pause_free_ratio": 0.1, "voice_reserve_mb": 768,
             "voice_lag_s": 0.5}
_sheds: dict[str, float] = {}       # source (`voice_loop`, `voice_audio`, `watchdog`) → its monotonic ceiling
#: Workers admitted and not yet RUNNING: key → «it runs (or is gone)». The next admission waits for them (T593).
_admitted: dict = {}


def shed(seconds: float, source: str) -> None:
    """`source` asks for room (the voice falling behind, the watchdog): hold new workers and relieve as under memory
    pressure, until `unshed(source)` or, as a safety ceiling only, `seconds` from now."""
    _sheds[source] = max(_sheds.get(source, 0.0), time.monotonic() + float(seconds))


def unshed(source: str) -> None:
    """The signal that raised `source`'s shed recovered: its hold ends now. Never releases another source's."""
    _sheds.pop(source, None)


def shedding() -> bool:
    """Any source still holding (its own recovery not yet read, its ceiling not yet passed)."""
    now = time.monotonic()
    return any(now < until for until in _sheds.values())


def policy() -> dict:
    """The declared envelope: the repo default, then the deployment's own file over it."""
    out = dict(_DEFAULTS)
    for path in (os.path.join(_HERE, n) for n in ("resources.default.json", "resources.json")):
        if not os.path.exists(path):     # the deployment's own file is optional
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                # every declared key, not only the envelope's own: the watchdog (T-28) and the summary (T-31) read here
                out.update({k: v for k, v in json.load(fh).items() if not k.startswith("_")})
        except Exception as e:  # noqa: BLE001 — a broken file says so and the defaults hold
            logger.warning(f"envelope: {path} unreadable ({e!r}) — the defaults hold")
    return out


def measured() -> tuple[int, int]:
    """`(total, available)` bytes of the host's memory, as it is NOW."""
    import psutil
    vm = psutil.virtual_memory()
    return int(vm.total), int(vm.available)


def floor(total: int, pol: dict | None = None) -> float:
    """The free memory a new worker must leave: the LARGER of the ratio and the voice's absolute reserve (T593) — on
    a small host the ratio alone is under what one voice session needs."""
    pol = pol or policy()
    return max(float(pol["admit_free_ratio"]) * total, float(pol.get("voice_reserve_mb", 0)) * 2 ** 20)


def admits(total: int, available: int, pol: dict | None = None) -> bool:
    return available >= floor(total, pol)


def under_pressure(total: int, available: int, pol: dict | None = None) -> bool:
    return available < float((pol or policy())["pause_free_ratio"]) * total


def preexec(also=None):
    """The worker's `preexec_fn`: lower scheduling priority than the voice, after `also` (a sandbox's own limits).
    Fail-soft (the child still runs)."""
    nice = int(policy()["worker_nice"])

    def _apply():
        if also is not None:
            also()
        if hasattr(os, "nice"):          # lowering one's own priority never needs a privilege on a Unix host
            os.nice(nice)
    return _apply


def settled() -> bool:
    """Every admitted worker already RUNS (or is gone): only then is the next one measured against the floor."""
    for key, runs in list(_admitted.items()):
        try:
            done = bool(runs())
        except Exception:  # noqa: BLE001 — a reading that fails counts as running: never a wedged gate
            done = True
        if done:
            _admitted.pop(key, None)
    return not _admitted


def released(key) -> None:
    """The admitted worker's slot ended (ran, failed or cancelled): it holds the gate no longer."""
    _admitted.pop(str(key), None)


def reason() -> str:
    """Why a new worker cannot start NOW — `waiting_room` (under the memory floor), `waiting_voice` (a shed held),
    `queued_behind` (the worker admitted before it is not running yet) — or "" when it can. Memory is named only
    when `admits()` is false (V2-867 T590: a 60 s «waiting for free memory» was a voice shed on a 70 % free host)."""
    if not admits(*measured()):
        return "waiting_room"
    if shedding():
        return "waiting_voice"
    if not settled():
        return "queued_behind"
    return ""


async def wait_for_room(say=None, *, key=None, runs=None, poll_s: float = 5.0) -> bool:
    """Hold a new worker until the host has room for it — for as long as it takes (V2-867 T592: a deadline made the
    envelope a delay, and the worker that «started anyway» is what starved the voice). `say(reason)` is called each
    time the reason changes. Once admitted, `key` holds the gate until `runs()` is true or `released(key)`. True."""
    said = ""
    while True:
        why = reason()
        if not why:
            break
        if why != said:
            said = why
            logger.info(f"envelope: worker {key or '?'} held — {why}")
            if say is not None:
                say(why)
        await asyncio.sleep(poll_s)
    if key is not None and runs is not None:      # no await between the reading and this: one admission per reading
        _admitted[str(key)] = runs
    return True


def relieve(records) -> str:
    """Under pressure pause the NEWEST running worker — only while ANOTHER keeps running, so the one errand he is waiting
    on is never the one frozen; with room again resume what it paused. Returns what it did."""
    total, avail = measured()
    live = sorted((r for r in records if getattr(r, "status", "") == "running" and getattr(r, "session", None)),
                  key=lambda r: float(getattr(r, "started", 0) or 0))
    if shedding() or under_pressure(total, avail):
        running = [r for r in live if not getattr(r, "paused", False)]
        newest = running[-1] if len(running) >= 2 else None
        if newest is not None and newest.session.pause():
            newest.paused_by = "envelope"          # only ITS pauses are undone here, never the operator's ⏻
            return f"paused {newest.task_id}"
    elif admits(total, avail) and not shedding():
        for r in live:
            if getattr(r, "paused_by", "") == "envelope" and r.session.resume():
                r.paused_by = ""
                return f"resumed {r.task_id}"
    return ""
