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
from nucleo.send import row as _row

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


#: The hand-overs that only LEAN to the messaging card: the owner's own reads decide what, if anything, was ordered.
LEANS = ("order", "our question")


async def _an_act_ordered(said: str, widget: str, last_line: str, before) -> dict | None:
    """The declared act (not a message) of the card his words order, chosen by the read among what the card declares
    — `{act, names}` — or None."""
    try:
        from nucleo.request import base
        from nucleo.send import read_act, turn
        from widgets import effects
        b = base(widget)
        from nucleo.workers import exit_risk
        # the acts that ASK (a lean never runs one unasked, and a harmless one needs fields a lean does not carry)
        acts = {name: str((sp or {}).get("desc") or "") for name, sp in (effects._manifest(b).get("actions") or {}).items()
                if isinstance(sp, dict) and turn.owned(b, name) and not turn.is_message(b, name)
                and exit_risk.asks_by_itself(b, name, {})}
        got = await asyncio.to_thread(read_act.choose, said, acts, last_line, before)
        return got if got.get("act") else None
    except Exception as e:  # noqa: BLE001
        _note(e)
        return None


def _orders_one(got: dict, by: str, act: str, h: dict | None = None) -> bool:
    """Do his words order a message? A read that is only a «yes» (nobody named, nothing said) orders none — unless the
    call names a card draft he can see (it carries its own text and person), or the model's own call carries a person
    and a text: his «yes, send it» to OUR offer «shall I tell X that…?» (he is read it, never sent it here)."""
    h = h or {}
    if got.get("unread"):
        return by in SURE
    if not got.get("mine") or got.get("drop"):
        return False
    offered = by in SURE and bool(str(h.get("contact") or h.get("to") or "").strip() and str(h.get("text") or "").strip())
    return bool(got.get("who") or got.get("text") or not got.get("send") or act in CARRIES_TEXT or offered)


def _same_person(d, other: str) -> bool:
    """Does the name a call carries point at the open draft's person — the one chosen, the name he said, or one of
    the people it is asking among? Then it is about THAT message, never a second one."""
    from nucleo.send import ask
    said = set(ask._fold(other).split())
    names = [d.target.get("name") if d.target else "", d.who] + [c.get("name") for c in d.candidates]
    return bool(said) and any(said <= set(ask._fold(n).split()) or set(ask._fold(n).split()) <= said
                              for n in names if n)


async def intake(said: str, hint: dict | None = None, last_line: str = "", before: list[str] | None = None,
                 by: str = "call") -> str:
    from nucleo.send import owner
    h = dict(hint or {})
    named_act = bool(h.get("_act"))              # the call (or the reading) NAMED an act; a lean names none
    act = str(h.pop("_act", "") or "send_to")
    widget = str(h.pop("_widget", "") or "mensajeria")
    row = str(h.pop("_row", "") or "")           # a queued message's own task, opened now (`open_the_next`)
    async with _lock():
        if (open_ := _draft.current()) is not None and row:
            return ""                            # another opened first: this one keeps waiting in the lane
        if open_ is None and not row and _row.busy():
            # the lane still holds a message (sent, its receipt not in yet): this one waits its turn behind it
            n = _draft.queue(said, {**h, "_act": act, "_widget": widget}, "worker" if by == "worker" else "queued")
            owner._emit("queued behind the message being sent", None, by=by, waiting=n)
            if by == "worker":
                return ""
            from nucleo.send import ask
            return await ask.line("send_queued", who=str(h.get("contact") or h.get("to") or ""), now=_row.sending_to())
        if open_ is not None:
            other = str(h.get("contact") or h.get("to") or "").strip()
            elsewhere = {}
            if not other and act in ("reply", "forward", "send_draft", "compose"):
                # a reply names its message, not a person: read it once now, and see whether it is THIS message's
                adopted = h.pop("_adopted", None) or await asyncio.to_thread(_deliver.adopt, act, h)
                t = adopted.get("target") or {}
                if t and not ((t.get("contact_id") and t.get("contact_id") == open_.target.get("contact_id"))
                              or (t.get("chat_id") and t.get("chat_id") == open_.target.get("chat_id"))):
                    elsewhere, other = adopted, str(t.get("name") or "")
            if not other and not elsewhere and by not in NO_READ:
                # a SURE order the call names nobody for: read on its own — a message to somebody else waits its turn
                fresh = await asyncio.to_thread(_read.read, said, _draft.Draft(said=said), last_line, before)
                if _orders_one(fresh, by, act, h) and fresh.get("who") and not _same_person(open_, fresh["who"]):
                    other = fresh["who"]
                    h = {**h, "contact": other, **({"text": fresh["text"]} if fresh.get("text") else {})}
            if by not in NO_READ and open_.asked == _draft.CONFIRM and (elsewhere or (other and not _same_person(
                    open_, other)) or (named_act and act != open_.act and open_.kind == "act")):
                # a NEW order while the open one only waits for his yes: he moved on. The new one is decided FIRST;
                # only when it opens is the first left undone (and said) — a queue behind a question he will not
                # answer would hold it for good, and a lean that orders nothing must cancel nothing
                lead = f"First say in a few words that «{open_.said[:120]}» was left undone — nothing was done."
                d = _draft.start(said)
                try:
                    async with d.lock:
                        line = await _open(d, said, h, act, last_line, before, by, widget, lead=lead)
                except BaseException:
                    _draft.close(d, _draft.CANCELLED)
                    _draft._open["draft"] = open_          # the first stands as it was
                    raise
                if not line or _draft.current() is not d and d.state == _draft.CANCELLED:
                    if _draft.current() is None:
                        _draft._open["draft"] = open_      # nothing new was ordered: the first stands as it was
                    return line
                open_.state = _draft.CANCELLED
                owner._emit("left undone for his new order", open_, by=by)
                return line
            if by in NO_READ or elsewhere or (other and not _same_person(open_, other)):
                h = {**h, **({"_adopted": elsewhere} if elsewhere else {})}
                n = _draft.queue(said, {**h, "_act": act, "_widget": widget}, "worker" if by == "worker" else "queued")
                owner._emit("queued behind the open draft", open_, by=by, waiting=n)
                if by == "worker":
                    return ""
                from nucleo.send import ask
                return await ask.line("send_queued", who=other, now=(open_.target or {}).get("name") or open_.who)
            taken, line = await owner.take(said, last_line=last_line, before=before, bounded=False)
            owner._emit("kept the open draft", open_, by=by, said=str(said)[:200], taken=taken)
            return line if taken else ""
        d = _draft.start(said, row=row)
        try:
            async with d.lock:                   # his next sentence waits for the draft to be built
                return await _open(d, said, h, act, last_line, before, by, widget)
        except BaseException as e:  # noqa: BLE001 — half-built (an error, a cut turn): closed, never left to read him
            _draft.close(d, _draft.CANCELLED)
            owner._emit("intake failed", d, why=f"{type(e).__name__}: {e}"[:200])
            raise


async def _open(d, said: str, h: dict, act: str, last_line: str, before, by: str, widget: str = "mensajeria",
                lead: str = "") -> str:
    from nucleo.send import owner
    d.by, d.act = by, act
    from nucleo.send import turn as _turn
    composes = _turn.composes(widget, act)          # a message to write (C2 A4): a message, never another act
    if not _turn.is_message(widget, act, h) and not composes:
        # an act that is not a message (a group created or left): the call carries what it is; the card says what
        # it would refuse and what it found, and asks its own question (`nucleo/send/act`)
        from nucleo.request import base
        d.kind, d.widget, d.extra = "act", base(widget), {k: v for k, v in h.items() if not str(k).startswith("_")}
        if by not in NO_READ:                    # his words name what the act is about; the call is a hint
            got = await asyncio.to_thread(_read.read, said, d, last_line, before)
            from nucleo.send import act as _act
            _act.take_names(d, got.get("names") or [], only_more=True)
        owner._emit("opened", d, by=by)
        return await owner._next(d, lead)
    adopted = await asyncio.to_thread(_deliver.adopt, act, {**h, "_compose": composes})
    d.extra = dict(adopted.get("extra") or {})
    got = dict(_read.NOTHING) if by in NO_READ else await asyncio.to_thread(_read.read, said, d, last_line, before)
    if by in LEANS and not _orders_one(got, by, act, h) and (chosen := await _an_act_ordered(said, widget, last_line,
                                                                                               before)):
        # not a message — an order of ANOTHER declared act of the card (leave the groups he names): that act's draft
        from nucleo.request import base
        d.kind, d.widget, d.act = "act", base(widget), chosen["act"]
        d.extra = {}
        from nucleo.send import act as _act
        _act.take_names(d, chosen["names"])
        owner._emit("opened", d, by=by, chosen=chosen["act"])
        return await owner._next(d, lead)
    if by not in NO_READ and not _orders_one(got, by, act, h):
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
    if got.get("at"):
        owner._when(d, got["at"])
    if who:
        owner._resolve(d, who, relation=str(h.get("relation") or ""))
    elif adopted.get("target"):            # a reply's conversation, a card draft's person: read once, by id
        d.target = dict(adopted["target"])
        d.who = d.target.get("name") or ""
    elif not got.get("unread") and (front := _people.open_conversation()).get("chat_id"):
        # nobody named in words that were READ: the conversation he has open (an unread sentence asks who)
        d.target, d.who = front, front.get("name") or ""
    owner._emit("opened", d, by=by, read=got)
    return await owner._next(d, lead)


_OPENING = {"on": False}


async def open_the_next() -> None:
    """The lane is free: the next message he asked for (or a worker handed over) is opened on its own task and asked
    out of turn. One at a time: the check and the pick happen before any await."""
    if _OPENING["on"] or _row.busy() or (nxt := _draft.next_queued()) is None:
        return
    _OPENING["on"] = True
    try:
        from nucleo.send import draft, owner
        line = await owner.intake(nxt["said"], {**nxt["hint"], "_row": nxt["row"]}, by=nxt["by"])
        if line:
            from nucleo.send import receipt
            d = draft.current()
            await receipt.say_out(line, f"send:next:{getattr(d, 'id', '')}")
    except Exception as e:  # noqa: BLE001
        _note(e)
    finally:
        _OPENING["on"] = False
