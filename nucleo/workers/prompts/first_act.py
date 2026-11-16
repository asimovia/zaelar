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
                   and payload_fill._base_of(str(d.get("wid") or "")) == base
                   for d in done_ops.recent(limit=done_ops._MAX))             # the whole book, not its last 8
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
    expands nothing inside (`$50`, backticks), a `'` is written `'\\''` — and a non-text value is `key:=<its JSON>`."""
    def arg(k, v):
        if isinstance(v, str):
            return f"{k}='" + v.replace("'", "'\\''") + "'"
        return f"{k}:='" + json.dumps(v, ensure_ascii=False).replace("'", "'\\''") + "'"   # typed: its JSON
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
                      do.format(command=command(wid, act, {k: "<…>" for k in required(wid, act, fields)}))])


def required(wid: str, act: str, fields: dict) -> list[str]:
    """The fields the command shows as placeholders: the ones the action needs. An optional one (its description says
    so, `payload_fill._optional` or a leading «opcional/optional») or a declared non-text one (a boolean the widget
    door converts) is listed above, never put in the command — a placeholder invites a value his words never gave."""
    from nucleo.flash import payload_fill
    from widgets import field_types
    typed = field_types.declared(payload_fill._base_of(wid), act)
    return [k for k, d in fields.items() if k not in typed and not payload_fill._optional(d)
            and not str(d or "").lower().lstrip().startswith(("opcional", "optional"))][:_FIELDS_SHOWN]


def parts(uid: str, context: dict | None, reading: dict | None, trace: str = "", seen: str = "") -> list[str]:
    """The handoff's blocks in reading order: his words (once — not when the prompt it joins, `seen`, or the recent
    conversation already carries them), the state now (`state_now`, refreshed by `act state`), the send row's block
    or the identified action's. Empty blocks left out."""
    out = []
    said = his_words(context)
    fold = lambda t: " ".join(str(t or "").lower().split())   # noqa: E731
    if said and fold(said) not in fold(seen) and not _already_heard(said) and (head := words("his_words_head")):
        out.append(f"{head}\n«{said}»")
    from nucleo.workers import state_now
    out.append(state_now.block(uid))
    from nucleo.request import send_task_words as _send_task
    out.append((_send_task.brief_block(uid) if uid else "") or act_block(reading, context, trace))
    return [p for p in out if p]


def block(uid: str, context: dict | None, reading: dict | None, trace: str = "", seen: str = "") -> str:
    """The handoff, in reading order (`parts`)."""
    return "\n\n".join(parts(uid, context, reading, trace, seen))


def live(prompt: str, uid: str, context: dict | None, reading: dict | None, trace: str = "") -> str:
    """A trusted worker's brief as composed: the prompt (with the surface's trusted blocks the dispatcher already
    appended), then the handoff. The ceiling is held by `fit`, over the brief exactly as it is SENT."""
    from nucleo.workers.prompts import catalog
    base = prompt
    tail = block(uid, context, reading, trace, seen=base)
    if tail:     # composed after the interpreter pass: its commands get the real interpreter here, like the rest
        from nucleo.workers.providers import claude as _c
        tail = catalog.with_py(tail, _c.bridge_python())
    return "\n\n".join(p for p in (base, tail) if p)


def _drop_order() -> tuple[str, ...]:
    """What `fit` may give up, in order, by the head its block opens with: ONLY the blocks this handoff adds — the
    state, his words, then the identified act last. The memory context, the conversation and the send row's block
    (sent before this handoff existed) are never cut by it: they ride as they always did."""
    return ("state_now.head", "his_words_head", "first_act_head")   # the send row's block is NOT new: never cut


def _span(text: str, head: str) -> tuple[int, int]:
    """`(start, end)` of the block that opens with `head` (up to the next blank line), or (-1, -1)."""
    i = text.find(head)
    while i > 0 and text[i - 2:i] != "\n\n":         # a block's head opens it: the same words inside one are not it
        i = text.find(head, i + 1)
    if i < 0:
        return -1, -1
    j = text.find("\n\n", i)
    return i, (len(text) if j < 0 else j)


def _said_dropped(key: str, size: int, total: int, cap: int) -> None:
    """A handoff block that did not fit is an EVENT, never a silence."""
    try:
        from voice.observer import emit
        emit("brain", "handoff block left out: over the brief's ceiling", role="system",
             text=f"{key} ({size} chars) — brief {total} > {cap}",
             extra={"cat": "worker", "block": key, "chars": size, "brief_chars": total, "ceiling": cap})
    except Exception as e:  # noqa: BLE001 — the log line below still says it
        _note("the drop event", e)
    logger.info(f"first_act: {key} left out of the brief ({size} chars; {total} > {cap})")


def fit(prompt: str, ceiling: int | None = None) -> str:
    """The brief as SENT: while over `PROMPT_CEILING_CHARS`, the blocks this handoff ADDED go, in `_drop_order` —
    each one said as an event. Nothing that was in the brief before the handoff is touched: a base that is over by
    itself (the hotel's, its memory, its conversation) is sent as it was, and the ceiling keeps measuring that base."""
    from nucleo.workers.prompts import catalog
    cap = catalog.PROMPT_CEILING_CHARS if ceiling is None else ceiling
    for key in _drop_order():
        if len(prompt) <= cap:
            break
        head = words(key).split("{", 1)[0].split("`", 1)[0]   # its fixed opening: up to the first format field or
        #                                                        command (the interpreter pass rewrites commands)
        start, end = _span(prompt, head) if head else (-1, -1)
        if start < 0:
            continue
        _said_dropped(key, end - start, len(prompt), cap)
        prompt = (prompt[:start].rstrip("\n") + ("\n\n" if end < len(prompt) else "") + prompt[end:].lstrip("\n")
                  ).strip("\n")
    return prompt
