"""An act toward a messaging platform that is not a message — a group created, a group left: the same owner, its own
question.

The card says what the act would refuse BEFORE he is asked (`widgets.contract.would_refuse`: a group he named that
is not among his, a member it cannot reach) and what it FOUND for his words (`exit_risk.ready_question`, the card's
`confirm_values`): the one confirmation names what will be acted on, never his raw words. An act whose declared type
runs on his order (`exit_risk.asks_by_itself` false: a group created with the people he named) is not asked. It runs
through the card's own act, and the final line is its receipt (the act's outbox row), as for a message.
"""
from __future__ import annotations

import asyncio

from loguru import logger


def _note(e: Exception) -> None:
    logger.debug(f"send.act: {type(e).__name__}: {e}")


def _what(d) -> str:
    """What he asked for, in his words — what the lines name («the groups you asked to leave»)."""
    return str(d.said or "")[:200]


async def line(d, moment: str, **fmt) -> str:
    """The line of `moment` (preparing · going · no · done · failed · late) for this act, worded from its fact."""
    from nucleo import wording
    return await wording.said(wording.line("act", moment), about=_what(d), **fmt)


def _found(d) -> list[str]:
    """The names the card found for this call (its confirmation's blanks), to check the worded question names them."""
    try:
        from nucleo.workers import exit_risk
        vals = exit_risk._card_values(d.widget, d.act, d.extra) or {}
        return [x.strip(" «»") for x in str(vals.get("groups") or vals.get("name") or "").split(",") if x.strip(" «»")]
    except Exception as e:  # noqa: BLE001
        _note(e)
        return []


async def next_step(d, lead: str = "") -> str:
    """What the act still lacks (said, and the draft closed: the conversation asks again), or its ONE confirmation, or
    — for a type that runs on his order — the act itself."""
    from nucleo.send import ask, draft, owner
    from nucleo.workers import exit_risk
    try:
        from widgets import contract
        refusal = await asyncio.to_thread(contract.would_refuse, d.widget, d.act, dict(d.extra))
    except Exception as e:  # noqa: BLE001 — unread: the act itself refuses later, said then
        _note(e)
        refusal = None
    if refusal:
        why = str(refusal.get("message") or refusal.get("error") or "")[:300]
        draft.close(d, draft.CANCELLED)
        owner._emit("act refused before asking", d, why=why)
        return await line(d, "failed", why=why)
    if not await asyncio.to_thread(exit_risk.asks_by_itself, d.widget, d.act, dict(d.extra)):
        d.asked, d.heard = draft.CONFIRM, True       # a type declared harmless runs on his order: no question
        owner._emit("runs on his order", d)
        return await owner._send(d)
    plain = await asyncio.to_thread(exit_risk.ready_question, d.widget, d.act, dict(d.extra))
    from nucleo import wording
    fact = wording.ready("act").format(plain=plain)
    worded = await wording.word_soon(f"{lead} Then: {fact}" if lead else fact, examples=(plain,), fallback=plain)
    found = _found(d)
    said = worded if all(ask._fold(f) in ask._fold(worded) for f in found) else plain   # it names what was found
    d.asked, d.heard, d.confirm_line = draft.CONFIRM, False, said
    owner._emit("asked", d, line=said[:200])
    return said


def list_field(d) -> str:
    """The ONE field of this act declared a list (`types`: the groups it leaves, the members it adds), or ""."""
    try:
        from widgets import field_types
        lists = [k for k, v in field_types.declared(d.widget, d.act).items() if v == field_types.LIST]
        return lists[0] if len(lists) == 1 else ""
    except Exception as e:  # noqa: BLE001
        _note(e)
        return ""


def take_names(d, names: list[str], *, only_more: bool = False) -> bool:
    """What HIS words name for the act fills its declared list field — his words over the model's call (measured: he
    named two groups, the call carried one). `only_more`: at intake, only when his words name more. True if it
    changed."""
    field = list_field(d)
    names = [str(n).strip() for n in names or () if str(n or "").strip()]
    if not field or not names:
        return False
    had = d.names_said()
    if only_more and len(names) <= len(had):
        return False
    from nucleo.send import ask
    if sorted(ask._fold(n) for n in names) == sorted(ask._fold(h) for h in had):
        return False                          # the same things named again: no change
    d.extra[field] = names
    return True


def run(d) -> dict:
    """The card's own act, blocking (call it off the loop)."""
    import importlib
    res = importlib.import_module(f"widgets.{d.widget}.data").apply_action(d.act, dict(d.extra))
    return res if isinstance(res, dict) else {"ok": False, "error": "no answer from the card"}
