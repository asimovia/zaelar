"""Who owns an act a card's own hand makes (C2 A3): a registry of claimants by the owner its event type declares.

`nucleo/events/vocabulary.py` says which door owns the acts of a type (`EventType.owner`); a manifest action says its
type (`effects.event_of`). The one funnel of outside mutations (`server_api._dispatch`) asks here, before the act
runs, whether that owner claims it: a claimant returns None to let the act run as always, or the answer itself. This
module knows nothing of any owner: each registers its own claimant (`register`).
"""
from __future__ import annotations

import logging

_claimants: dict = {}
_settlers: dict = {}      # owner → what it does with an act's RESULT, once the act ran (a send the card held is not his)
_log = logging.getLogger("zaelar.widgets")


def register(owner: str, fn, settle=None) -> None:
    _claimants[str(owner)] = fn
    if settle is not None:
        _settlers[str(owner)] = settle


def _owner(wid: str, act: str) -> str:
    from nucleo.events import vocabulary

    from . import effects
    return vocabulary.owner_of(effects.event_of(wid, act))


def claim(wid: str, act: str, payload: dict) -> dict | None:
    """The answer of the owner of this act's type, or None: the act runs as it would."""
    try:
        fn = _claimants.get(_owner(wid, act))
        return fn(wid, act, payload) if fn is not None else None
    except Exception as e:  # noqa: BLE001 — a claimant that fails never stops his act
        _log.debug(f"owners: the claim of {wid}:{act} failed ({e!r})")
        return None


def settle(wid: str, act: str, payload: dict, res) -> None:
    """The owner of this act's type reads what the act answered — after it ran, never before."""
    try:
        if (fn := _settlers.get(_owner(wid, act))) is not None:
            fn(wid, act, payload, res)
    except Exception as e:  # noqa: BLE001 — a settler that fails never changes what his act did
        _log.debug(f"owners: the settle of {wid}:{act} failed ({e!r})")
