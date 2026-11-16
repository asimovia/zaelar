"""nucleo/request/channel_twin.py — an act that leaves through a channel, called with NO channel named, becomes the act
its card DECLARES for that case.

Measured: «crea un grupo cena con Ana y Luis» reached `mensajeria:create_group` (a WhatsApp/Telegram group) and asked
«to whom?», while what he meant was a group of his CONTACTS; with no channel connected no group was possible at all.
The decision is the cards', never a word table: an action that leaves declares `"without_channel": {"act":
"<widget>:<action>", "keys": {<its key>: <the twin's key>}}`, and when the call carries no channel and the turn's
reading SAYS there is none (its `message_channel` verdict landed as `none`), the twin runs with the mapped payload. Any
sign of a channel, a first message, or a reading that does not say (absent, unlanded) keeps the leaving act.
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


def _channel_said(wid: str, action: str, raw: dict, folded: dict, reading) -> bool:
    """ANY sign of a channel: a value under the channel slot's key or one of its declared synonyms (in the call as it
    came or folded), a first message (a group you write to is a chat group), no reading at all to rule it out, or the
    turn's channel reading naming one at ANY confidence. Only its total absence lets the twin run — a doubt keeps the
    leaving act, which names its channel or is refused saying so."""
    from nucleo.request import base
    from nucleo.request.send_task import filled
    from nucleo.workers import exit_slots
    from widgets.contract import synonyms
    slots = exit_slots.declared(base(wid), action)
    for _slot, d in slots.items():
        key = str(d.get("key") or "")
        if d.get("from") == "reading":   # the key and every synonym the contract declares for it
            keys = synonyms(key)
        else:
            keys = {key} if d.get("from") == "composed" else set()
        if any(filled(p.get(k)) for p in (raw, folded) for k in keys):
            return True
    if reading is None:
        return True
    try:
        from nucleo.acts import message_channel
        if isinstance(reading, dict):         # the carried reading: its channel verdict at ANY confidence
            v = (reading.get("result") or {}).get(message_channel.KEY)
            choice = v.get("choice") if isinstance(v, dict) else None
        else:                                 # the live brief: reading it fires its door; unlanded is a doubt
            from nucleo.turn import verdicts
            choice, info = verdicts.read(reading, message_channel.KEY, None, min_confidence=0.0)
            choice = choice if info is not None else None
        return choice != message_channel.NONE   # only a reading that SAYS «no channel» lets the twin run
    except Exception as e:  # noqa: BLE001 — unread: the leaving act keeps its own route
        logger.debug(f"channel_twin: the channel reading unread ({e!r})")
        return True


def twin(wid: str, action: str, payload: dict | None, reading=None) -> tuple[str, str, dict] | None:
    """`(widget, action, payload)` of the declared twin when it is CERTAIN no channel was named, else None."""
    decl = _spec(wid, action).get("without_channel")
    if not isinstance(decl, dict) or ":" not in str(decl.get("act") or ""):
        return None
    raw = dict(payload or {})
    folded = raw
    try:
        from widgets import contract
        from nucleo.request import base
        folded = contract.fold_aliases(base(wid), action, raw)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"channel_twin: aliases unread ({e!r})")
    if _channel_said(wid, action, raw, folded, reading):
        return None
    to_wid, _sep, to_act = str(decl["act"]).partition(":")
    keys = decl.get("keys") if isinstance(decl.get("keys"), dict) else {}
    mapped = {str(keys[k]): v for k, v in folded.items() if k in keys}
    return to_wid, to_act, mapped
