"""One turn's reading of the screen: each open card's published rows read once, the screen question built once
(`brief_screen`; held by `brief.build` around its whole table)."""
from __future__ import annotations

import contextlib
from contextvars import ContextVar

#: One turn's reading of the screen (`one_read`): each card's published rows, and the screen question once built.
_TURN: ContextVar = ContextVar("brief_screen_turn", default=None)


@contextlib.contextmanager
def one_read():
    """While this is held, every question of the brief reads each open card's index ONCE and builds the screen
    question once. The brief's table asks the screen question three times (itself and the two catalogue gates) and the
    row question reads the indexes again: four whole reads of every open card per turn, on the voice loop."""
    token = _TURN.set({})
    try:
        yield
    finally:
        _TURN.reset(token)


def _rows(base: str) -> list:
    """The rows `base` publishes — read once inside `one_read`, every time outside it."""
    from widgets import refs as _refs
    memo = _TURN.get()
    if memo is None:
        return _refs._ref_index(base)
    if ("rows", base) not in memo:
        memo[("rows", base)] = _refs._ref_index(base)
    return memo[("rows", base)]
