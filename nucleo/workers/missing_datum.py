"""A datum only he can give stops the worker at ONE question — held by the bridge, not asked for in the playbook.

Measured: a worker whose card refused its act for a missing name went on to ~20 chained searches for more than 15
minutes; nothing in the mechanism stopped it, and a search cannot find what he never said. So when a card REFUSES a
worker's `widget_data` and the refusal DECLARES the field it lacks (`field`, the shape of the widget contract's
`selector_missing` and of any card that says which datum is missing), the row holds that missing datum: from then on
the bridge lets through only the question to him (`ask_user`, which parks the session), a read (a widget, its card,
the state), or the act again. Any other act is refused with the datum it lacks. The hold is cleared when the act runs
or once his question is registered on the row — never by a question to a network agent. A refusal that names no
field holds nothing: the bridge never guesses which datum was missing (a «not found», a channel down, our own
exception are not his data). No counter and no cap. The hold rides on the row (artefact `missing_datum`), so a
worker that restarts before asking is still held.
"""
from __future__ import annotations

from loguru import logger

#: What a held row still lets through: the one question, a read (a widget, its card, the state), the act again.
_PASSES = ("ask_user", "read_widget", "widget_data", "state", "card")
SLOT = "missing_datum"


def _store():
    from nucleo.circuit import ledger
    return ledger.store()


def _write(rec, value: dict) -> None:
    rec.missing_datum = value
    uid = str(getattr(rec, "uid", "") or "")
    if not uid:
        return
    try:
        _store().artifact_put(uid, SLOT, value)
    except Exception as e:  # noqa: BLE001 — the hold still lives on the record
        logger.debug(f"missing_datum: hold of {uid} not written ({e!r})")


def _current(rec) -> dict:
    """The row's hold: the record's, else the row's artefact (a restarted worker), read once."""
    got = getattr(rec, "missing_datum", None)
    if got is None:
        uid = str(getattr(rec, "uid", "") or "")
        try:
            got = (_store().artifact_get(uid, SLOT) if uid else None) or {}
        except Exception as e:  # noqa: BLE001
            logger.debug(f"missing_datum: hold of {uid} unread ({e!r})")
            got = {}
        rec.missing_datum = got
    return got if isinstance(got, dict) else {}


def on_refusal(rec, call: dict, res: dict) -> dict:
    """A card's refusal of a worker's act: when it DECLARES the field it lacks, the row holds it and says so."""
    if not isinstance(res, dict) or res.get("ok") is not False or not isinstance(call, dict):
        return res
    wid = str(call.get("widget_id") or call.get("id") or "").strip().lower()
    act = str(call.get("action") or "").strip()
    field = str(res.get("field") or "").strip()
    if not (wid and act and field):
        return res
    _write(rec, {"widget": wid, "action": act, "fields": [field]})
    return {**res, "missing": [field], "error": f"{res.get('error') or ''} — {reason(rec)}".strip(" —")}


def reason(rec) -> str:
    """Why the row is held, in the bridge's words ('' when nothing is missing)."""
    m = _current(rec)
    if not m:
        return ""
    return (f"`{m['widget']}:{m['action']}` lacks {', '.join(m['fields'])} — a datum only he can give. Ask him ONE "
            f"question now (`python -m nucleo.cli.bridge ask \"…\"`): that ends your turn and his answer resumes it. "
            f"Searching does not find what he did not say.")


def held(rec, action: str) -> str:
    """The refusal for an act a held row does not let through, or ''."""
    if action in _PASSES or not _current(rec):
        return ""
    return reason(rec)


def clear(rec) -> None:
    if _current(rec):
        _write(rec, {})
    rec.missing_datum = {}
