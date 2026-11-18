"""His order to send: a NEW draft, read from his words — the model's call (read ONCE by `deliver.adopt`) fills what the
read left empty. It never sends: the line it returns is always a question, and a message leaves only on his yes to the
confirmation that read him its text.

One intake at a time (`_LOCK`): a worker's hand-over and a turn's never build two drafts over each other. While a draft
is open, a NEW order is never lost and never overwrites it: a call naming somebody else waits its turn behind it
(and he is told so); anything else of the same turn is read again, with no clock, as a sentence about the open one.
"""
from __future__ import annotations

import asyncio

from loguru import logger

from nucleo.send import deliver as _deliver
from nucleo.send import draft as _draft
from nucleo.send import people as _people
from nucleo.send import read as _read

#: The hand-overs that carry the model's or the verdict's own reading of a message: an UNREAD read of his words opens
#: the draft from that reading (and asks), never loses his order.
SURE = ("call", "held call", "brief")
#: Hand-overs whose words are not his to read now: a worker's act, a message queued from an earlier sentence.
NO_READ = ("worker", "queued")
#: The model's message acts that name what they send: a card draft or composed message carries its own text.
CARRIES_TEXT = ("send_draft", "compose")

_LOCK: dict = {"lock": None}


def _lock() -> asyncio.Lock:
    if _LOCK["lock"] is None:
        _LOCK["lock"] = asyncio.Lock()
    return _LOCK["lock"]


def _note(e: Exception) -> None:
    logger.debug(f"send.intake: {type(e).__name__}: {e}")


def _orders_one(got: dict, by: str, act: str) -> bool:
    """Do his words order a message? A read that is only a «yes» (nobody named, nothing said) orders none — unless the
    call names a card draft he can see, which carries its own text and person."""
    if got.get("unread"):
        return by in SURE
    if not got.get("mine") or got.get("drop"):
        return False
    return bool(got.get("who") or got.get("text") or not got.get("send") or act in CARRIES_TEXT)


async def intake(said: str, hint: dict | None = None, last_line: str = "", before: list[str] | None = None,
                 by: str = "call") -> str:
    from nucleo.send import owner
    h = dict(hint or {})
    act = str(h.pop("_act", "") or "send_to")
    async with _lock():
        if (open_ := _draft.current()) is not None:
            other = str(h.get("contact") or h.get("to") or "").strip()
            if by in NO_READ or (other and not owner._names_the_chosen(open_, other)
                                 and other.lower() != (open_.who or "").lower()):
                n = _draft.queue(said, {**h, "_act": act}, "worker" if by == "worker" else "queued")
                owner._emit("queued behind the open draft", open_, by=by, waiting=n)
                if by == "worker":
                    return ""
                from nucleo.send import ask
                return await ask.line("send_queued", who=other, now=(open_.target or {}).get("name") or open_.who)
            taken, line = await owner.take(said, last_line=last_line, before=before, bounded=False)
            owner._emit("kept the open draft", open_, by=by, said=str(said)[:200], taken=taken)
            return line if taken else ""
        d = _draft.start(said)
        d.by, d.act = by, act
        adopted = await asyncio.to_thread(_deliver.adopt, act, h)
        d.extra = dict(adopted.get("extra") or {})
        got = dict(_read.NOTHING) if by in NO_READ else await asyncio.to_thread(_read.read, said, d, last_line, before)
        if by not in NO_READ and not _orders_one(got, by, act):
            # Only HIS words order a message. A call, a verdict or a lean over words that do not («a bare yes», «stop
            # repeating me», «forget that message») opens nothing.
            _draft.close(d, _draft.CANCELLED)
            owner._emit("not a message", d, by=by, read=got)
            return ""
        who = got.get("who") or str(h.get("contact") or h.get("to") or "").strip()
        text = got.get("text") if got.get("text") is not None else (
            " ".join(str(adopted.get("text") or h.get("text") or "").split()) or None)
        d.channel = got.get("channel") or str(h.get("channel") or h.get("platform") or "").strip().lower()
        if text:
            d.text = text
        if who:
            owner._resolve(d, who, relation=str(h.get("relation") or ""))
        elif adopted.get("target"):            # a reply's conversation, a card draft's person: read once, by id
            d.target = dict(adopted["target"])
            d.who = d.target.get("name") or ""
        owner._emit("opened", d, by=by, read=got)
        return await owner._next(d)


async def open_the_next() -> None:
    """The draft ended: the next message he asked for (or a worker handed over) is opened and asked out of turn."""
    nxt = _draft.next_queued()
    if nxt is None:
        return
    try:
        from nucleo.send import draft
        line = await intake(nxt["said"], nxt["hint"], by=nxt["by"])
        if line:
            from nucleo.pulse import notices
            d = draft.current()
            await notices.notify("zaelar", line, key=f"send:next:{getattr(d, 'id', '')}", kind="info")
    except Exception as e:  # noqa: BLE001
        _note(e)
