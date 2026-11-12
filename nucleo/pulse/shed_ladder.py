"""nucleo/pulse/shed_ladder.py — how the engine gives memory back, one declared rung at a time (V2-891).

Measured on the operator's machine (a 48 GB host with 33 of 35 GB of swap in use and a 31.7 GB local model resident):
the self watchdog said «shedding load (nothing to pause)» 279 times in one session. It had ONE lever — pause the
newest Brain Worker while another runs — and with no worker running it had nothing, while the voice went deaf. The
pressure was not ours, and the engine still had things to give back.

So the levers are a LADDER, in a declared order (`config/resources.default.json` → `shed_ladder`), each rung a name
with an actuator registered by the body:

    hold_workers         no new Brain Worker starts (the envelope's hold)
    pause_newest_worker  the newest running worker is paused (never the only one he is waiting on)
    pause_background     the widgets' background ticks stop
    close_browser        the idle search Chromium is closed (it starts again on the next search)
    trim_caches          the body collects garbage and hands freed pages back to the OS

The rule, pure (no I/O — `step` reads a reading and returns one action):
  · under pressure (free memory under the floor, or the voice's lag over its bound) → ENGAGE the next rung, one per
    step, whatever the cause: `cause` says whose memory it is — `engine` when our own processes are over their
    declared budgets, `machine` when we are within them and the host is short anyway — and the event names it, but
    the ladder descends for both, because the voice suffers the same either way;
  · recovered WITH MARGIN (free ≥ floor × `shed_recover_ratio` and the lag under its bound) → RELEASE the last rung
    engaged, one per step, in reverse order;
  · in between → hold where it is (no flapping on the floor).
"""
from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_LADDER = ("hold_workers", "pause_newest_worker", "pause_background", "close_browser", "trim_caches")
DEFAULT_RECOVER = 1.15


def ladder_of(pol: dict | None) -> tuple:
    declared = (pol or {}).get("shed_ladder")
    if isinstance(declared, (list, tuple)) and declared:
        return tuple(str(r) for r in declared)
    return DEFAULT_LADDER


def cause(engine_mb: float, engine_budget_mb: float) -> str:
    """`engine` when our processes hold more than their declared budgets, `machine` when the host is short anyway."""
    return "engine" if engine_mb > engine_budget_mb else "machine"


def pressure(reading: dict) -> bool:
    free, floor_mb = float(reading.get("free_mb", 0)), float(reading.get("floor_mb", 0))
    lag, bound = float(reading.get("voice_lag_s", 0) or 0), float(reading.get("lag_bound_s", 0) or 0)
    return free < floor_mb or (bound > 0 and lag >= bound)


def recovered(reading: dict, recover_ratio: float = DEFAULT_RECOVER) -> bool:
    free, floor_mb = float(reading.get("free_mb", 0)), float(reading.get("floor_mb", 0))
    lag, bound = float(reading.get("voice_lag_s", 0) or 0), float(reading.get("lag_bound_s", 0) or 0)
    return free >= floor_mb * recover_ratio and not (bound > 0 and lag >= bound)


@dataclass
class Ladder:
    rungs: tuple = DEFAULT_LADDER
    recover_ratio: float = DEFAULT_RECOVER
    engaged: list = field(default_factory=list)

    def step(self, reading: dict) -> dict | None:
        """One reading → at most one action: `{"engage": rung, "cause": …}` · `{"release": rung}` · None."""
        if pressure(reading):
            for rung in self.rungs:
                if rung not in self.engaged:
                    self.engaged.append(rung)
                    return {"engage": rung, "cause": str(reading.get("cause") or "machine"),
                            "depth": len(self.engaged)}
            return None                            # every rung is down: nothing more to give
        if self.engaged and recovered(reading, self.recover_ratio):
            rung = self.engaged.pop()
            return {"release": rung, "depth": len(self.engaged)}
        return None

    def depth(self) -> int:
        return len(self.engaged)


def from_policy(pol: dict | None) -> Ladder:
    return Ladder(rungs=ladder_of(pol), recover_ratio=float((pol or {}).get("shed_recover_ratio", DEFAULT_RECOVER)))
