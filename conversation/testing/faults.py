"""P8 skeleton: kill the process before or after each transition, then restart on the same store (§9, node 13.23).

A `Crash` is a `BaseException`: no handler of the package catches it — a run's own failure handling (`except
Exception`) is for failures, not for the process disappearing. Every transaction it interrupts rolls back; what was
committed stays. `inject(point, when)` arms ONE crash: the next call of that point raises before running (`before`)
or right after returning (`after`), once.

Points (the transitions of §9): `accept` an envelope · `close` a revision (its phase noted) · `seal` a revision ·
`reserve` an effect · `submit` (the provider is about to be called) · `provider` (the provider answered, nothing
recorded yet) · `receipt` (the answer recorded) · `ack` (a playout acknowledgement).

Declared for F2, not simulated here (they need a real provider): webhooks duplicated or out of order, a late callback
of a cancelled run, a restored older database. Their place is the same: the gateway's reconciliation looks, never
resends.
"""
from __future__ import annotations

from contextlib import contextmanager
from enum import Enum

from conversation.gateway import dispatch, seal
from conversation.inbox.mailbox import Inbox
from conversation.ledger.book import BookTx
from conversation.mouth.say import Speaker


class Crash(BaseException):
    """The process died here."""


class Point(Enum):
    ACCEPT, CLOSE, SEAL, RESERVE = "accept", "close", "seal", "reserve"
    SUBMIT, PROVIDER, RECEIPT, ACK = "submit", "provider", "receipt", "ack"


def _targets(point: Point, tools) -> tuple[object, str]:
    if point is Point.ACCEPT:
        return Inbox, "accept"
    if point is Point.CLOSE:
        return seal, "note"
    if point is Point.SEAL:
        return seal, "seal"
    if point is Point.RESERVE:
        return BookTx, "open_unique"
    if point is Point.ACK:
        return Speaker, "ack"
    if point is Point.RECEIPT:
        return dispatch, "submit"                # after it returns: the provider's answer is recorded
    return tools, "call"                         # SUBMIT (before) / PROVIDER (after) around the provider's call


@contextmanager
def inject(point: Point, when: str, tools=None):
    """Arm one crash at `point` (`when` = before | after). Restores the original on the way out."""
    owner, name = _targets(point, tools)
    original = getattr(owner, name)
    fired = {"n": 0}
    is_async = point in (Point.SUBMIT, Point.PROVIDER, Point.RECEIPT)
    if point is Point.SUBMIT:
        when = "before"
    if point in (Point.PROVIDER, Point.RECEIPT):
        when = "after"

    def armed() -> bool:
        if fired["n"]:
            return False
        fired["n"] = 1
        return True

    if is_async:
        async def wrapper(*a, **kw):
            if when == "before" and armed():
                raise Crash(f"{point.value}/before")
            out = await original(*a, **kw)
            if when == "after" and armed():
                raise Crash(f"{point.value}/after")
            return out
    else:
        def wrapper(*a, **kw):
            if when == "before" and armed():
                raise Crash(f"{point.value}/before")
            out = original(*a, **kw)
            if when == "after" and armed():
                raise Crash(f"{point.value}/after")
            return out
    setattr(owner, name, wrapper)
    try:
        yield fired
    finally:
        setattr(owner, name, original)
