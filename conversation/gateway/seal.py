"""I1/I3: a revision is SEALED by its first effect or its first publication; a seal and a reopen exclude each other.

The intervention's row carries one field, `phase` = "<revision>:<state>". Sealing is a compare-and-set from
"n:closed" to "n:sealed"; reopening is a compare-and-set from "n:closed" (or "n:incomplete") to "n+1:open". Both
start from the same value, so exactly one of them wins — in the same store, from any number of writers. A sealed
revision never reopens: the voice that follows is an amendment (the ear makes it a new intervention). An incomplete
revision is never sealed: it is not actionable.

`note` records what the ear said and only moves FORWARD: never to a lower revision, never off a seal — a re-delivered
older revision (an adapter that retries) cannot pull the phase back and make a reopened revision sealable. A reopen
that is discarded (its words were echo, or it never had any) gives the phase back to the revision it reopened; a
reopen nobody is finishing (the process that heard it is gone) is given back after a bound (`abandon`).
"""
from __future__ import annotations

T = "interventions"


def phase(rev: int, state: str) -> str:
    return f"{rev}:{state}"


def _split(row: dict | None) -> tuple[int, str]:
    if row is None:
        return 0, ""
    rev, _, state = row["phase"].partition(":")
    return int(rev), state


def note(tx, iv: str, rev: int, state: str, now: int) -> bool:
    """Record a revision's state (closed · incomplete · discarded), forward only. True when it was written."""
    row = tx.get(T, iv)
    cur_rev, cur_state = _split(row)
    if cur_state == "sealed" or rev < cur_rev:
        return False
    if state == "discarded" and rev > 1 and rev == cur_rev and row is not None and row.get("prev"):
        return tx.cas(T, iv, "phase", row["phase"], {"phase": row["prev"], "rev": rev - 1, "prev": None,
                                                     "updated_ms": now})
    new = {**(row or {}), "phase": phase(rev, state), "rev": rev, "updated_ms": now}
    if state == "closed":
        new["closed_ms"] = now
    if row is None:
        tx.put(T, iv, new)
        return True
    return tx.cas(T, iv, "phase", row["phase"], new)


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
                                                         "prev": phase(rev, frm), "updated_ms": now})
               for frm in ("closed", "incomplete"))


def abandon(tx, iv: str, now: int) -> bool:
    """A reopen nobody is finishing: give the phase back to the revision it reopened (compare-and-set)."""
    row = tx.get(T, iv)
    _rev, state = _split(row)
    if state != "open" or not row.get("prev"):
        return False
    return tx.cas(T, iv, "phase", row["phase"], {"phase": row["prev"], "rev": row["rev"] - 1, "prev": None,
                                                 "updated_ms": now})


def open_since(tx, iv: str) -> tuple[int, int] | None:
    """(revision, since) of a reopened revision still open, or None."""
    row = tx.get(T, iv)
    rev, state = _split(row)
    return (rev, row.get("updated_ms", 0)) if state == "open" else None


def sealed_rev(tx, iv: str) -> int | None:
    rev, state = _split(tx.get(T, iv))
    return rev if state == "sealed" else None
