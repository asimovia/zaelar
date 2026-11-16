"""nucleo/request/channel_twin.py — an act that leaves through a channel, called with NO channel named, becomes the act
its card DECLARES for that case.

Measured: «crea un grupo cena con Ana y Luis» reached `mensajeria:create_group` (a WhatsApp/Telegram group) and asked
«to whom?», while what he meant was a group of his CONTACTS; with no channel connected no group was possible at all.
The decision is the cards', never a word table: an action that leaves declares `"without_channel": {"act":
"<widget>:<action>", "keys": {<its key>: <the twin's key>}}`, and when the call carries no channel and the turn's
reading names none, the twin runs with the mapped payload. He names the channel → the leaving act, as before.
"""
from __future__ import annotations

from loguru import logger


def _spec(wid: str, action: str) -> dict:
    try:
        from widgets import runtime
        from nucleo.request import base
        got = ((runtime.get(base(wid)) or {}).get("actions") or {}).get(action) or {}
        return got if isinstance(got, dict) else {}
    except Exception as e:  # noqa: BLE001
        logger.debug(f"channel_twin: {wid}:{action} unread ({e!r})")
        return {}


def _channel_named(wid: str, action: str, payload: dict, reading) -> bool:
    """The call carries a channel, or the turn's reading names one (`message_channel`)."""
    from nucleo.request import base
    from nucleo.request.send_task import _reading_names, filled
    from nucleo.workers import exit_slots
    for _slot, d in exit_slots.declared(base(wid), action).items():
        if d.get("from") == "reading":
            v = payload.get(str(d.get("key") or ""))
            if filled(v):
                return True
    try:
        from nucleo.acts import message_channel
        from nucleo.turn import brief as _tb, verdicts
        turn = _tb.revived(reading) if isinstance(reading, dict) else reading
        choice, _info = verdicts.read(turn, message_channel.KEY, None) if turn is not None else (None, None)
        return choice not in (None, message_channel.NONE)
    except Exception as e:  # noqa: BLE001 — unread: the leaving act keeps its own route
        logger.debug(f"channel_twin: the channel reading unread ({e!r})")
        return True


def twin(wid: str, action: str, payload: dict | None, reading=None) -> tuple[str, str, dict] | None:
    """`(widget, action, payload)` of the declared twin when no channel is named, else None."""
    decl = _spec(wid, action).get("without_channel")
    if not isinstance(decl, dict) or ":" not in str(decl.get("act") or ""):
        return None
    p = dict(payload or {})
    try:
        from widgets import contract
        from nucleo.request import base
        p = contract.fold_aliases(base(wid), action, p)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"channel_twin: aliases unread ({e!r})")
    if _channel_named(wid, action, p, reading):
        return None
    to_wid, _sep, to_act = str(decl["act"]).partition(":")
    keys = decl.get("keys") if isinstance(decl.get("keys"), dict) else {}
    mapped = {str(keys[k]): v for k, v in p.items() if k in keys}
    return to_wid, to_act, mapped
