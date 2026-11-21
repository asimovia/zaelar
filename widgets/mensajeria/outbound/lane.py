"""widgets/mensajeria/outbound/lane.py — WHO asked for a send, carried from the door that took the order to the queue.

Every order this card queues for a connector names its lane (`connectors/exit.py`): the road that asked for it. The
lane is not a field a caller fills in the order — it is set ONCE, by the code of the door that took the act, under the
reserved payload key `_lane`, and read here for the length of that one `apply_action` call. An action that runs
another (`forward` → `send_to`, a mail draft saved and sent) keeps the lane it came in with.

An act with no lane, or with a lane the switch holds, is refused where it would queue (`passes` raises `Held`): the
card answers «not sent» with the reason, and nothing is written.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

from connectors import exit as door
from widgets import effects as _fx      # the acts that always queue are declared on the manifest (`always_leaves`)

#: The reserved payload key. Its value counts only as a `door.Stamp` — the same letters written by a model are no lane.
KEY = "_lane"

_lane: ContextVar[str] = ContextVar("mensajeria_lane", default="")


class Held(Exception):
    """An order that may not be queued: `why` is the exit door's reason."""

    def __init__(self, why: str) -> None:
        super().__init__(why)
        self.why = why


@contextmanager
def of(payload: dict | None):
    """The lane of ONE action: the payload's own when it carries one, else the lane already in force (an action run by
    another), else none."""
    named = (payload or {}).get(KEY)
    token = _lane.set(door.stamped(named)) if named is not None else None
    try:
        yield
    finally:
        if token is not None:
            _lane.reset(token)


def current() -> str:
    return _lane.get()


def passes(kind: str, lane: str = "", order: dict | None = None) -> str:
    """The lane this order leaves with — or `Held` when it may not be queued (counted and recorded by the door)."""
    lane = str(lane or current())
    why = door.check(kind, lane, order)
    if why:
        raise Held(why)
    return lane


def refusal(why: str) -> dict:
    """What a held act answers: nothing was sent, and why."""
    from ..words import say
    return {"ok": False, "error": "held", "held": why,
            "message": say("held_outbound", "Sending is paused on this account right now, so nothing was sent.")}


def early(action: str, payload: dict | None, *, sends: bool = False) -> dict | None:
    """The read-only veto for an act that would queue an order (`data.answer_action`): refused before it is queued,
    answered to whoever asked. None when it may go on, or when the act does not always leave — unless the caller
    knows this one sends now (`sends`: the card's own Send)."""
    p = payload or {}
    if not sends and not _fx.always_leaves("mensajeria", action) and not (
            action == "reply" and str(p.get("text") or "").strip()):
        return None
    why = door.check(action, door.stamped(p.get(KEY)) or current())
    return refusal(why) if why else None
