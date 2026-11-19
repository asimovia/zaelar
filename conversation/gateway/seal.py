"""I1/I3: an intervention is SEALED by its first effect or its first publication, and a sealed one never changes.

The intervention's row carries one field, `phase`: the state the ear ended it in (`closed` · `incomplete` ·
`discarded`), then `sealed` (its first effect or publication) or `final` (its request ended without one). An
intervention is the unit: what the person says after its close is ANOTHER intervention that amends it, so nothing ever
moves a phase back, and nothing moves it forward but a seal or the request's end.

`note` records how the ear ended it — once: the first note wins, a re-delivered one changes nothing. `seal` is a
compare-and-set from `closed` (an incomplete or discarded intervention is not actionable and never seals). `finish`
is the request's end: `final`, unless it was already sealed.
"""
from __future__ import annotations

T = "interventions"


def note(tx, iv: str, state: str, now: int) -> bool:
    """Record how the ear ended an intervention, once. True when it was written."""
    if tx.get(T, iv) is not None:
        return False
    row = {"phase": state, "updated_ms": now}
    if state == "closed":
        row["closed_ms"] = now
    tx.put(T, iv, row)
    return True


def seal(tx, iv: str, now: int) -> bool:
    """True when the intervention is sealed — now, or already (a final one cannot be reopened either). False when it
    never closed."""
    row = tx.get(T, iv)
    if row is None:
        return False
    if row["phase"] in ("sealed", "final"):
        return True
    return tx.cas(T, iv, "phase", "closed", {"phase": "sealed", "sealed_ms": now, "updated_ms": now})


def finish(tx, iv: str, now: int) -> None:
    """Its request ended: `final`, unless sealed (a sealed intervention stays sealed)."""
    row = tx.get(T, iv)
    if row is None or row["phase"] in ("sealed", "final"):
        return
    tx.cas(T, iv, "phase", row["phase"], {"phase": "final", "final_ms": now, "updated_ms": now})


def phase(tx, iv: str) -> str | None:
    row = tx.get(T, iv)
    return row["phase"] if row else None
