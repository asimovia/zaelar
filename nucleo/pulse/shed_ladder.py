"""nucleo/pulse/shed_ladder.py — how the engine gives memory back, one declared rung at a time (V2-891).

Measured (a 48 GB host, 33 of 35 GB of swap in use, a 31.7 GB local model resident): «shedding load (nothing to
pause)» 279 times in one session — ONE lever (pause the newest worker while another runs), nothing with no worker
running, while the voice went deaf. The pressure was not ours, and the engine still had things to give back.

So the levers are a LADDER, in a declared order (`config/resources.default.json` → `shed_ladder`), each rung a name
with an actuator registered by the body:

    hold_workers         no new Brain Worker starts (the envelope's hold)
    pause_newest_worker  the newest running worker is paused (never the only one he is waiting on)
    pause_background     the widgets' background ticks stop
    close_browser        the idle search Chromium is closed (it starts again on the next search)
    trim_caches          the body collects garbage and hands freed pages back to the OS

The rule, pure (`step` reads a reading, returns one action): under pressure (free memory under the floor, or the body
loop stalled in two beats running) → ENGAGE the next rung, one per step, whatever `cause` names (the voice suffers the
same); recovered WITH MARGIN (free ≥ floor × `shed_recover_ratio`, no stall this beat) → RELEASE the last one, in
reverse; in between → hold (no flapping on the floor).
"""
from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_RECOVER = 1.15


def ladder_of(pol: dict | None) -> tuple:
    """The declared rungs, in order. Undeclared → none: a ladder nobody declared gives nothing back."""
    declared = (pol or {}).get("shed_ladder")
    return tuple(str(r) for r in declared) if isinstance(declared, (list, tuple)) else ()


def cause(engine_mb: float, engine_budget_mb: float, loop_ours_s: float = 0.0, loop_host_s: float = 0.0,
          loop_unknown_s: float = 0.0, short: bool = False) -> str:
    """`engine`: ours over budget, or our own work held the loop longest (E3); `machine`: memory `short` (read BEFORE
    the loop) or the host's stalls; `unknown`: unattributed stalls dominate (never named the host's)."""
    if engine_mb > engine_budget_mb or (not short and loop_ours_s > max(loop_host_s, loop_unknown_s)):
        return "engine"
    return "unknown" if not short and loop_unknown_s > loop_host_s else "machine"


def pressure(reading: dict) -> bool:
    """Free memory under the floor, or the body loop's PERSISTING stall over its bound (E0; the voice sheds itself)."""
    lag, bound = float(reading.get("loop_lag_s", 0) or 0), float(reading.get("lag_bound_s", 0) or 0)
    return float(reading.get("free_mb", 0)) < float(reading.get("floor_mb", 0)) or (bound > 0 and lag >= bound)


def recovered(reading: dict, recover_ratio: float = DEFAULT_RECOVER) -> bool:
    """Free memory over floor × margin and NO stall in THIS beat (`loop_lag_now_s`, else the persisting one)."""
    free, floor_mb = float(reading.get("free_mb", 0)), float(reading.get("floor_mb", 0))
    now = float(reading.get("loop_lag_now_s", reading.get("loop_lag_s", 0)) or 0)
    return free >= floor_mb * recover_ratio and now <= 0


@dataclass
class Ladder:
    rungs: tuple = ()
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
