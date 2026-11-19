"""I1/I3: a revision is SEALED by its first effect or its first publication; a seal and a reopen exclude each other.

The intervention's row carries one field, `phase` = "<revision>:<state>". Sealing is a compare-and-set from
"n:closed" to "n:sealed"; reopening is a compare-and-set from "n:closed" (or "n:incomplete") to "n+1:open". Both
start from the same value, so exactly one of them wins — in the same store, from any number of writers. A sealed
revision never reopens: the voice that follows is an amendment (the ear makes it a new intervention). An incomplete
revision is never sealed: it is not actionable.
"""
from __future__ import annotations

T = "interventions"


def phase(rev: int, state: str) -> str:
    return f"{rev}:{state}"


def note(tx, iv: str, rev: int, state: str, now: int) -> None:
    """Record what the ear said about a revision (closed / incomplete), unless it is already sealed."""
    row = tx.get(T, iv)
    if row is not None and row["phase"].endswith(":sealed"):
        return
    tx.put(T, iv, {**(row or {}), "phase": phase(rev, state), "rev": rev, "updated_ms": now,
                   **({"closed_ms": now} if state == "closed" else {})})


def seal(tx, iv: str, rev: int, now: int) -> bool:
    """True when the revision is sealed — now, or already. False when it was reopened (or never closed)."""
    row = tx.get(T, iv)
    if row is None:
        return False
    if row["phase"] == phase(rev, "sealed"):
        return True
    return tx.cas(T, iv, "phase", phase(rev, "closed"), {"phase": phase(rev, "sealed"), "sealed_ms": now})


def reopen(tx, iv: str, rev: int, now: int) -> bool:
    """Revision `rev` → `rev + 1` open, only if `rev` is closed or incomplete and NOT sealed."""
    return any(tx.cas(T, iv, "phase", phase(rev, frm), {"phase": phase(rev + 1, "open"), "rev": rev + 1,
                                                         "updated_ms": now})
               for frm in ("closed", "incomplete"))


def sealed_rev(tx, iv: str) -> int | None:
    row = tx.get(T, iv)
    if row is None or not row["phase"].endswith(":sealed"):
        return None
    return int(row["phase"].split(":")[0])
