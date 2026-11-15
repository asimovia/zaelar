"""The handoff from Flash to its worker: his literal sentence and the act the turn identified, as the worker's FIRST step.

Measured: an errand whose act the turn had already identified (a card, an action with declared fields) reached its
worker as a paraphrase with neither — the worker rediscovered the card by chained searches for minutes and never
ran the act. The turn's reading already travels on the row (`rec.reading`, V2-852) but only the exit door read it.

So the worker's brief carries, once, as DATA: his words verbatim (`task.context["said"]`, the sentence of the turn
that commissioned it) and — when the turn's `screen_action` verdict is sure and names an action the card declares —
that action with its declared fields and the one bridge call that runs it. It generalises what a send row already
had (`send_task_words.brief_block`): a send row keeps its own block (its slots carry their sources); any other
declared action gets this one. Nothing here decides intent: the verdict was paid for in the turn, the card declares
the fields, and the worker composes the values from his words.
"""
from __future__ import annotations

import json

from loguru import logger

#: How much of a field's declared description its line carries: the card's own words, cut — the full card is a call away.
_FIELD_CAP = 110


def _note(what: str, e: Exception) -> None:
    logger.debug(f"first_act: {what} unread ({type(e).__name__}: {e})")


def his_words(context: dict | None) -> str:
    """His sentence verbatim, as the turn heard it ('' when the task carries none)."""
    ctx = context or {}
    return str(ctx.get("said") or ctx.get("heard") or "").strip()


def identified(reading: dict | None) -> tuple[str, str, dict]:
    """`(card, action, {field: description})` the carried reading surely names, the action declared by the card; else
    ("", "", {}). Sure = the verdicts' licence, the same floor every other reader of the reading uses."""
    try:
        from nucleo.turn import brief as _tb, verdicts
        handle = _tb.revived(reading)
        if handle is None:
            return "", "", {}
        choice, info = verdicts.read(handle, _tb.TARGET_KEY, None)
        wid, _sep, act = str(choice or "").partition(":")
        if not (info and wid and act):
            return "", "", {}
        from nucleo.flash import frontend as _fe, payload_fill
        if act not in (_fe.declared_actions(payload_fill._base_of(wid)) or {}):
            return "", "", {}
        return wid, act, dict(payload_fill._payload_spec(wid, act))
    except Exception as e:  # noqa: BLE001 — an unread reading leaves the brief as it was
        _note("the reading", e)
        return "", "", {}


def words(key: str) -> str:
    from nucleo.workers.prompts import catalog
    return catalog.words(key)


def act_block(reading: dict | None) -> str:
    """The identified action as the worker's first step: its fields and the one call ('' when none is identified)."""
    wid, act, fields = identified(reading)
    head, line, do = words("first_act_head"), words("first_act_field"), words("first_act_do")
    if not (wid and head and line and do):
        return ""
    rows = [line.format(field=k, desc=str(v or "").replace("\n", " ")[:_FIELD_CAP]) for k, v in fields.items()]
    call = json.dumps({"widget_id": wid, "action": act, "payload": {k: "<…>" for k in fields}}, ensure_ascii=False)
    return "\n".join([head.format(widget=wid, action=act), *rows, do.format(call=call)])


def block(uid: str, context: dict | None, reading: dict | None) -> str:
    """Everything the handoff hands over: his words, then the send row's block or the identified action's."""
    parts = []
    said = his_words(context)
    if said and (head := words("his_words_head")):
        parts.append(f"{head}\n«{said}»")
    from nucleo.request import send_task_words as _send_task
    act = _send_task.brief_block(uid) if uid else ""
    parts.append(act or act_block(reading))
    return "\n\n".join(p for p in parts if p)
