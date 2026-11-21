"""When a lead-in cover last SOUNDED (V2-529, V2-535) — read by the response-onset measure (`agent_events`), which
says whether the wait he lived was covered.

The cover itself (a «Look…», «Un segundo…» sounded while the old turn's model still thought) went with the old turn's
voice node (INI-078 F2): nothing sounds one now, so the clock stays at 0.0 until a cover exists again.
"""
from __future__ import annotations

_last_fired_at = 0.0


def last_fired_at() -> float:
    """Monotonic timestamp of the last cover that actually sounded (0.0 if none this process)."""
    return _last_fired_at
