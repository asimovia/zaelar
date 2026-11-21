"""Which acts are a message's and which its owner composes — read off the act's declared event, never a name.

A message to somebody (its event type's family is `send`) is its owner's (`nucleo/send`): the conversation host hands
it over instead of running it (`conversation_host/acts`, `acts_widget`); an act that writes or drops a message being
written in its card (a LOCAL type the send owner owns) is the owner's draft, never a second one in the card; every
act that leaves toward a messaging platform is the owner's too (`owned`).
"""
from __future__ import annotations

from loguru import logger


def _note(e: Exception) -> None:
    logger.debug(f"send.turn: {type(e).__name__}: {e}")


def is_message(wid: str, action: str, payload: dict | None = None) -> bool:
    """Is this act a message to somebody (its event type's family), as opposed to any other act that leaves?"""
    try:
        from nucleo.request import base
        from nucleo.request import send_receipt
        return bool(wid and action) and send_receipt.family(base(wid), action, payload or {}) == "send"
    except Exception as e:  # noqa: BLE001
        _note(e)
        return False


def composes(wid: str, action: str) -> bool:
    """Does this act write or drop a message being written in its card — a LOCAL type the send owner owns? Read off the
    act's declared event (`effects.event_of`) and the vocabulary's owner: no widget's or action's name here (C2)."""
    try:
        from nucleo.events import vocabulary as _voc
        from widgets import effects
        t = _voc.of(effects.event_of(wid, action))
        return t is not None and t.direction == _voc.LOCAL and t.owner == "send"
    except Exception as e:  # noqa: BLE001 — unreadable: not a composition, the act runs as it would
        _note(e)
        return False


def owned(wid: str, action: str, payload: dict | None = None) -> bool:
    """Is this an act that LEAVES toward a messaging platform — a message, a group created, a group left — by the event
    type it declares (`messaging.*`)? Every such act is the owner's; any other act that leaves is not."""
    try:
        from nucleo.request import base
        from nucleo.workers import exit_risk
        from widgets import effects
        b = base(wid)
        return bool(b and action) and effects.leaves(b, action) and \
            exit_risk.klass(b, action, payload or {}).startswith("messaging.")
    except Exception as e:  # noqa: BLE001
        _note(e)
        return False
