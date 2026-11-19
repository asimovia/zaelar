"""A7: a hold received BEFORE an effect is submitted blocks it; after submission it changes nothing.

A hold is a signal from one of his devices (he started speaking, he pressed «wait», a stop) recorded with its time.
It blocks every claimed effect of the account that has not been submitted yet. It is never released by time — a
sleeping tab cannot veto forever, because the release does not ask every device: a GESTURE on the device that
initiated the effect commits it. No other device, and no clock, can.
"""
from __future__ import annotations

T = "holds"


def hold(tx, hold_id: str, endpoint: str, t_ms: int, reason: str) -> dict:
    row = tx.get(T, hold_id) or {"id": hold_id, "endpoint": endpoint, "t_ms": t_ms, "reason": reason,
                                 "released": []}
    tx.put(T, hold_id, row)
    return row


def blocking(tx, effect: dict) -> list[dict]:
    """The holds that block this effect: received after it was claimed, not released for it."""
    claimed = effect["created_ms"]
    return [r for _k, r in tx.scan(T) if r["t_ms"] >= claimed and effect["id"] not in r["released"]]


def release(tx, effect: dict, endpoint: str | None, gesture: bool) -> bool:
    """Commit a held effect: only a gesture on the device that initiated it."""
    if not gesture or endpoint != effect["data"].get("endpoint"):
        return False
    for key, row in tx.scan(T):
        if row["t_ms"] >= effect["created_ms"] and effect["id"] not in row["released"]:
            row["released"].append(effect["id"])
            tx.put(T, key, row)
    return True
