"""I6: every accepted envelope ends accounted for — told, coalesced, silent on purpose, expired, or applied by id —
and until then it is in a state with a clock: queued, held (until its cap), deferred (until its due time, never past
the must-tell cap), or dequeued into a run. Nothing sits in limbo.

`audit` reads a snapshot and returns the violations as sentences; P3 calls it after every random case and the
mailbox test after every scenario. It reads; it never repairs.
"""
from __future__ import annotations

from conversation.config import Config
from conversation.inbox.mailbox import FINAL, RowState, T

LIVE = frozenset(m.value for m in RowState) - {RowState.ACCOUNTED.value}


def audit(snapshot, now: int, cfg: Config, *, drained: bool = False) -> list[str]:
    """`drained=True` once the manager has nothing left to run: then only accounted rows are acceptable."""
    bad = []
    for key, row in snapshot.scan(T):
        state = row["state"]
        if state == "accounted":
            if row["outcome"] not in FINAL:
                bad.append(f"{key}: accounted with outcome {row['outcome']!r}")
            continue
        if state not in LIVE:
            bad.append(f"{key}: unknown state {state!r}")
        elif drained:
            bad.append(f"{key}: still {state} after the inbox drained")
        elif state == "held" and (row["hold_until"] is None or now > row["hold_until"]):
            bad.append(f"{key}: held past its cap")
        elif state == "deferred":
            cap = row["accepted"] + cfg.must_tell_max_defer_ms
            if row["due"] is None or (row["must_tell"] and row["due"] > cap):
                bad.append(f"{key}: deferred without a due time inside the must-tell cap")
    return bad


def outcomes(snapshot) -> dict[str, str]:
    return {k: r["outcome"] for k, r in snapshot.scan(T) if r["state"] == "accounted"}
