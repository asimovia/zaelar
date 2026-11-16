"""nucleo/turn/rerouted.py — a model call another card's act served in its place, this turn (by trace).

Measured: `mensajeria:create_group` with no channel ran as `contactos:create_group` (`request/channel_twin`), the group
was made and checked, and the turn still said «that was not done in Messages»: `unserved.calls_not_run` reads the
model's calls, and the card it named was never touched. A call some door served elsewhere is noted here, and the
turn's words are composed from the act that RAN (its card answers for it), never from the call it replaced.
"""
from __future__ import annotations

_BY_TRACE: dict[str, set[tuple[str, str]]] = {}


def _trace() -> str:
    from nucleo.turn import reply
    return reply._trace()


def note(card: str, action: str) -> None:
    """This turn's call `card:action` was served by another card's act."""
    from nucleo.request import base
    _BY_TRACE.setdefault(_trace(), set()).add((base(card), str(action or "")))
    while len(_BY_TRACE) > 32:
        _BY_TRACE.pop(next(iter(_BY_TRACE)))


def was(card: str, action: str) -> bool:
    from nucleo.request import base
    return (base(card), str(action or "")) in _BY_TRACE.get(_trace(), set())
