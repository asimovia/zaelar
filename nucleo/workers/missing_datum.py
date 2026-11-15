"""A datum only he can give stops the worker at ONE question — held by the bridge, not asked for in the playbook.

Measured: a worker whose card refused its act for a missing name went on to ~20 chained searches for more than 15
minutes; nothing in the mechanism stopped it, and a search cannot find what he never said. So when a card REFUSES a
worker's `widget_data` and the refusal names its field (`field`, the contract's shape) or the call left a field the
action declares as required empty, the row holds that missing datum: from then on the bridge lets through only the
question to him (`ask_user`, which ends the session's turn — `_register_ask` parks it), a read of a card, or the act
again with the datum filled. Any other act is refused with the datum it lacks. The hold clears when the act runs or
when the question is asked. No counter and no cap: the hold is a fact of the row, not a budget.
"""
from __future__ import annotations

from loguru import logger

#: What a held row still lets through: the one question, a card's read, and the act again (with the datum filled).
_PASSES = ("ask_user", "read_widget", "widget_data")

#: How a manifest marks a field the act may go without (the word, anywhere in its description).
_OPTIONAL = ("opcional", "optional")


def _optional(desc) -> bool:
    d = str(desc or "").lower()
    return any(w in d for w in _OPTIONAL)


def required_empty(wid: str, act: str, payload: dict | None) -> list[str]:
    """The fields the action declares as required that this call left empty, in declared order."""
    try:
        from nucleo.flash import payload_fill
        spec = payload_fill._payload_spec(wid, act)
    except Exception as e:  # noqa: BLE001 — an unreadable declaration names no missing field
        logger.debug(f"missing_datum: {wid}:{act} unread ({e!r})")
        spec = {}
    pl = payload if isinstance(payload, dict) else {}
    return [k for k, d in spec.items() if not _optional(d) and pl.get(k) in (None, "", [], {})]


def on_refusal(rec, call: dict, res: dict) -> dict:
    """A card's refusal of a worker's act: when it lacks a datum, the row holds it and the refusal says so."""
    if not isinstance(res, dict) or res.get("ok") is not False or not isinstance(call, dict):
        return res
    wid = str(call.get("widget_id") or call.get("id") or "").strip().lower()
    act = str(call.get("action") or "").strip()
    named = str(res.get("field") or "").strip()
    fields = [named] if named else required_empty(wid, act, call.get("payload"))
    if not (wid and act and fields):
        return res
    rec.missing_datum = {"widget": wid, "action": act, "fields": fields}
    return {**res, "missing": fields, "error": f"{res.get('error') or ''} — {reason(rec)}".strip(" —")}


def reason(rec) -> str:
    """Why the row is held, in the bridge's words ('' when nothing is missing)."""
    m = getattr(rec, "missing_datum", None) or {}
    if not m:
        return ""
    return (f"`{m['widget']}:{m['action']}` lacks {', '.join(m['fields'])} — a datum only he can give. Ask him ONE "
            f"question now (`python -m nucleo.cli.bridge ask \"…\"`): that ends your turn and his answer resumes it. "
            f"Searching does not find what he did not say.")


def held(rec, action: str) -> str:
    """The refusal for an act a held row does not let through, or ''."""
    if not getattr(rec, "missing_datum", None) or action in _PASSES:
        return ""
    return reason(rec)


def clear(rec) -> None:
    rec.missing_datum = None
