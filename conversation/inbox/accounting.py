"""I6: every accepted envelope ends accounted for — told, silent on purpose, expired, applied by id, or failed — and
until then it is in a state with a clock: queued, held (until its cap), or dequeued into a run. Nothing sits in limbo.

`audit` reads a snapshot and returns the violations as sentences; P3 calls it after every random case and the
mailbox test after every scenario. It reads; it never repairs.
"""
from __future__ import annotations

from conversation.config import Config
from conversation.inbox.mailbox import FINAL, RowState, T

LIVE = frozenset(m.value for m in RowState) - {RowState.ACCOUNTED.value}


def audit(snapshot, now: int, cfg: Config, *, drained: bool = False, running: set | None = None) -> list[str]:
    """`drained=True` once the manager has nothing left to run: then only accounted rows are acceptable. `running`:
    the batch numbers of the runs in course — a non-control row dequeued into any other batch is orphaned."""
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
        elif (state == "dequeued" and row["kind"] == "user.control"
              and now - row["accepted"] > cfg.control_bound_ms):
            bad.append(f"{key}: a control accepted and never handled")
        elif (state == "dequeued" and row["kind"] != "user.control" and running is not None
              and row["batch"] not in running):
            bad.append(f"{key}: dequeued into batch {row['batch']}, which no run is running")
        elif state == "held" and (row["hold_until"] is None or now > row["hold_until"]):
            bad.append(f"{key}: held past its cap")
    return bad


def outcomes(snapshot) -> dict[str, str]:
    return {k: r["outcome"] for k, r in snapshot.scan(T) if r["state"] == "accounted"}
