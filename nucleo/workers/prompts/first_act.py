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

#: The handoff's bounds, so the live brief stays under `catalog.PROMPT_CEILING_CHARS` whatever the turn carried: a
#: field's description (the card's own words, cut — the whole card is `cli.widget card` away), how many fields are
#: listed, and how much of his sentence rides when the recent conversation does not already carry it whole.
_FIELD_CAP = 70
_FIELDS_SHOWN = 8
_WORDS_CAP = 300


def _note(what: str, e: Exception) -> None:
    logger.debug(f"first_act: {what} unread ({type(e).__name__}: {e})")


def his_words(context: dict | None) -> str:
    """His sentence verbatim, as the turn heard it ('' when the task carries none), cut at `_WORDS_CAP`."""
    ctx = context or {}
    return str(ctx.get("said") or ctx.get("heard") or "").strip()[:_WORDS_CAP]


def _already_heard(said: str) -> bool:
    """The recent conversation already carries his sentence whole: it rides once, there."""
    try:
        from nucleo.workers.prompts.context import _recent_conversation_block
        fold = lambda t: " ".join(str(t or "").lower().split())   # noqa: E731
        return bool(said) and fold(said) in fold(_recent_conversation_block())
    except Exception as e:  # noqa: BLE001
        _note("the recent conversation", e)
        return False


def owns_the_act(context: dict | None) -> bool:
    """The turn's act belongs to THIS errand only when the turn commissioned one errand: `heard` is his sentence for
    the ONE errand it commissions and empty for each of several (`pipeline_errands`), and a `part` is one of several."""
    ctx = context or {}
    return bool(str(ctx.get("heard") or "").strip()) and "part" not in ctx


def ran_in_the_turn(wid: str, act: str, reading: dict | None, trace: str = "") -> bool:
    """The turn already executed this act (the session's ledger of executed ops, by the turn's trace)."""
    traces = {t for t in (str((reading or {}).get("turn_id") or ""), str(trace or "")) if t}
    try:
        from nucleo import done_ops
        from nucleo.flash import payload_fill
        base = payload_fill._base_of(wid)
        return any(str(d.get("trace") or "") in traces and d.get("action") == act
                   and payload_fill._base_of(str(d.get("wid") or "")) == base for d in done_ops.recent())
    except Exception as e:  # noqa: BLE001
        _note("the turn's ops", e)
        return False


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


def command(wid: str, act: str, payload: dict) -> str:
    """The ONE shell command that runs the act: its fields as `key=value` arguments (`cli.widget data`), so the
    worker spends one model turn per act, not a Write and then a Bash. Every value is SINGLE-quoted — the shell
    expands nothing inside (`$50`, backticks), a `'` is written `'\\''` — and a non-text value is its JSON."""
    def arg(k, v):
        text = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        return f"{k}='" + text.replace("'", "'\\''") + "'"
    return " ".join(["python -m nucleo.cli.widget data", wid, act, *(arg(k, v) for k, v in payload.items())])


def act_block(reading: dict | None, context: dict | None = None, trace: str = "") -> str:
    """The identified action as the worker's first step: its fields and the one call — '' when none is identified,
    when it is not THIS errand's (`owns_the_act`) or when the turn already ran it (`ran_in_the_turn`)."""
    if not owns_the_act(context):
        return ""
    wid, act, fields = identified(reading)
    head, line, do = words("first_act_head"), words("first_act_field"), words("first_act_do")
    if not (wid and head and line and do) or ran_in_the_turn(wid, act, reading, trace):
        return ""
    shown = list(fields.items())[:_FIELDS_SHOWN]
    rows = [line.format(field=k, desc=str(v or "").replace("\n", " ")[:_FIELD_CAP]) for k, v in shown]
    if len(fields) > len(shown):
        rows.append(f"  · +{len(fields) - len(shown)}: `cli.widget card {wid}`")
    return "\n".join([head.format(widget=wid, action=act), *rows,
                      do.format(command=command(wid, act, {k: "<…>" for k, _v in shown}))])


#: Reading order of the handoff's blocks (the priority order, what is dropped last first, is `parts`').
_READING = ("words", "state", "act")


def parts(uid: str, context: dict | None, reading: dict | None, trace: str = "") -> list[tuple[str, str]]:
    """The handoff's blocks in PRIORITY order, `(kind, text)`: the send row's block or the identified action's, his
    words (once — not when the recent conversation carries them), the state now (`state_now`, refreshed by
    `act state`). Empty blocks left out."""
    from nucleo.request import send_task_words as _send_task
    out = [("act", (_send_task.brief_block(uid) if uid else "") or act_block(reading, context, trace))]
    said = his_words(context)
    if said and not _already_heard(said) and (head := words("his_words_head")):
        out.append(("words", f"{head}\n«{said}»"))
    from nucleo.workers import state_now
    out.append(("state", state_now.block(uid)))
    return [(k, t) for k, t in out if t]


def block(uid: str, context: dict | None, reading: dict | None, trace: str = "", budget: int | None = None) -> str:
    """The handoff in reading order (his words, the state, the act). With a `budget`, a block that does not fit is
    dropped, lowest priority first — the ceiling holds by construction."""
    kept, used = {}, 0
    for kind, text in parts(uid, context, reading, trace):
        if budget is None or used + len(text) + 2 <= budget:
            kept[kind] = text
            used += len(text) + 2
    return "\n\n".join(kept[k] for k in _READING if k in kept)


def live(prompt: str, surface: str, uid: str, context: dict | None, reading: dict | None, trace: str = "") -> str:
    """A trusted worker's brief as it LEAVES the dispatcher: the composed prompt, the surface's trusted blocks, the
    handoff — one function, so the ceiling test measures exactly what the worker reads."""
    from nucleo.workers.prompts.catalog import PROMPT_CEILING_CHARS
    from nucleo.workers.prompts.surfaces import trusted_blocks
    base = prompt + trusted_blocks(surface)
    tail = block(uid, context, reading, trace, budget=PROMPT_CEILING_CHARS - len(base) - 2)
    return "\n\n".join(p for p in (base, tail) if p)
