"""A datum only he can give stops the worker at ONE question — held by the bridge, not asked for in the playbook.

Measured: a worker whose card refused its act for a missing name went on to ~20 chained searches for more than 15
minutes; nothing in the mechanism stopped it, and a search cannot find what he never said. So when a card REFUSES a
worker's `widget_data` and the refusal DECLARES that its CAUSE is an absent datum — the card's `missing: <field>`, or
the widget contract's `selector_missing` with its `field` — and the call did leave that field empty, the row holds it: from then on
the bridge lets through only the question to him (`ask_user`, which parks the session), a read (a widget, its card,
the state), or the act again. Any other act is refused with the datum it lacks. The hold is cleared when the act runs
or once his question is registered on the row — never by a question to a network agent. A refusal that names no
field holds nothing: the bridge never guesses which datum was missing (a «not found», a channel down, our own
exception are not his data). `field` alone is NOT a cause: `widgets/action_shape` adds it to every refusal as a shape
hint (measured: `agenda:update_task` «task not found» held the row on `list`). No counter and no cap. The hold rides
on the row (artefact `missing_datum`), so a worker the engine restarts mid-session is still held; every session close
clears it (`session_finish._closing`), so a relay or a reopened row is never born held.
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
    field = cause(res)
    sent = call.get("payload") if isinstance(call.get("payload"), dict) else {}
    if not (wid and act and field) or sent.get(field) not in (None, "", [], {}) or _under_another_key(wid, act, sent):
        return res
    _write(rec, {"widget": wid, "action": act, "fields": [field]})
    return {**res, "missing": [field], "error": f"{res.get('error') or ''} — {reason(rec)}".strip(" —")}


def _under_another_key(wid: str, act: str, sent: dict) -> bool:
    """The call carried a value under a key the action does not declare: the datum came, on the WRONG key — the
    worker can fix that from the refusal; it is not a datum only he can give (`cancel_meeting {meeting: "x"}`)."""
    try:
        from nucleo.flash import payload_fill
        declared = set(payload_fill._payload_spec(wid, act))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"missing_datum: {wid}:{act} unread ({e!r})")
        return False
    return bool(declared) and any(k not in declared and v not in (None, "", [], {}) for k, v in sent.items())


def cause(res: dict) -> str:
    """The absent datum a refusal DECLARES as its cause ('' when it declares none): the card's `missing`, or the
    contract's empty selector (`selector_missing` + `field`). Any other `field` is a shape hint, not a cause."""
    from widgets.contract import SELECTOR_MISSING
    if str(res.get("missing") or "").strip():
        return str(res["missing"]).strip()
    return str(res.get("field") or "").strip() if res.get("error") == SELECTOR_MISSING else ""


def after(rec, action: str, call: dict, res: dict) -> dict:
    """Every executed `widget_data` (the bridge's and the retained act his yes runs): one that ran clears the hold,
    one refused for a declared absent datum sets it."""
    if rec is None or action != "widget_data" or not isinstance(res, dict):
        return res
    if res.get("ok") is not False and not res.get("error"):
        clear(rec)
        return res
    return on_refusal(rec, call or {}, res)


def reason(rec) -> str:
    """Why the row is held, in the bridge's words ('' when nothing is missing)."""
    m = _current(rec)
    if not m:
        return ""
    from nucleo.workers.providers.claude import bridge_python
    return (f"`{m['widget']}:{m['action']}` lacks {', '.join(m['fields'])} — a datum only he can give. Ask him ONE "
            f"question now (`{bridge_python()} -m nucleo.cli.bridge ask \"…\"`): that ends your turn and his answer "
            f"resumes it. Searching does not find what he did not say.")


def held(rec, action: str) -> str:
    """The refusal for an act a held row does not let through, or ''."""
    if action in _PASSES or not _current(rec):
        return ""
    return reason(rec)


def clear(rec) -> None:
    if _current(rec):
        _write(rec, {})
    rec.missing_datum = {}
