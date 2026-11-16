"""nucleo/dispatch/siblings.py — two errands his ONE turn commissioned are siblings, never one the refinement of the other.

The dispatcher's dedup folds an escalation into a live or parked errand that looks like it. One of several errands of a
turn (`part`, V2-844) must still meet that dedup against errands of EARLIER turns (his repetition is the same errand),
but never against a sibling of its own turn: «crea un grupo … y búscame un restaurante» folded the restaurant into the
group's errand and one worker got both. A sibling is an errand whose carried reading names the same turn.
"""
from __future__ import annotations


def _turn(ctx: dict | None) -> str:
    return str(((ctx or {}).get("reading") or {}).get("turn_id") or "")


def same_turn(ctx: dict | None, tid: str) -> bool:
    """`tid` (a live or parked errand) was commissioned by the same turn as this escalation, which is one of its parts."""
    if (ctx or {}).get("part") is None or not tid:
        return False
    mine = _turn(ctx)
    if not mine:
        return False
    from nucleo import dispatch as _d
    rec = _d.get_record(str(tid))
    theirs = _turn({"reading": getattr(rec, "reading", None)}) if rec is not None else ""
    if not theirs:
        parked = (_d._PENDING_CONFIRM.get(str(tid)) or {}).get("context") or {}
        theirs = _turn(parked)
    return bool(theirs) and theirs == mine
