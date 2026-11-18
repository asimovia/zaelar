"""The owner of a send: intake, every sentence about it, the one question, the send on his yes, the receipt.

`intake(said, hint)` — the turn hands over his words (and the model's call as a hint). Returns the line the turn says;
it NEVER sends: a message leaves only on his yes to the confirmation that read him its text.
`take(said, …)` — at the turn's gate, before anything else routes his words: True when the sentence was about the open
send (answered here, at once); False when it is not (the conversation answers it). Never swallows what it cannot read.

What happens next is decided here and nowhere else, by code over the draft, one sentence at a time (`Draft.lock`):
  · nobody resolved → resolve the name (`people`): one → chosen; several → ask which, naming them; nobody → ask who;
  · no text → ask what to tell her;
  · both → what would stop it is said first (`deliver.check`: a channel to choose, no way to reach her); then ONE
    confirmation that reads the text verbatim (`ask.confirm`);
  · his go-ahead → the card's own act with the person's row id, followed to the connector's receipt. A bare «yes»
    counts only as the answer to that confirmation, said last; otherwise he is read it again.
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger

from nucleo.send import ask as _ask
from nucleo.send import deliver as _deliver
from nucleo.send import draft as _draft
from nucleo.send import people as _people
from nucleo.send import read as _read
from nucleo.send import receipt as _receipt

#: The hand-over that only LEANS to a message (an order on the messaging card, no message act read): when the owner's
#: read says his words are not a message, the turn goes on as any other. Every other hand-over the read refuses is
#: DROPPED — no other lane may act on a message.
LEAN = "order"
#: The hand-overs that carry the model's or the verdict's own reading of a message: an UNREAD read of his words opens
#: the draft from that reading (and asks), never loses his order.
SURE = ("call", "held call", "brief")


def _note(e: Exception) -> None:
    logger.debug(f"send.owner: {type(e).__name__}: {e}")


def _emit(label: str, d, **extra) -> None:
    try:
        from voice.observer import emit
        emit("send", f"📨 send · {label}", text=(d.text if d else "")[:200], role="system",
             extra={"cat": "flash", "event": "send", "step": label, **({"draft": d.snapshot()} if d else {}), **extra})
    except Exception as e:  # noqa: BLE001 — the record never decides the send
        _note(e)


# ── the next step, by code ──────────────────────────────────────────────────────────────────────────────────────────
def _resolve(d, who: str) -> None:
    """Point the draft at the person `who` names (among the candidates it was asking about, when it was)."""
    was = list(d.candidates)
    got = _people.chosen(who, was, d.channel) if was else _people.resolve(who, d.channel)
    if was and not (got.get("one") or got.get("several")):
        return                                   # a name nobody carries keeps the question he was asked
    d.who, d.target, d.candidates, d.unmatched = who, {}, [], []
    d.unread = bool(got.get("unread"))
    if got.get("one"):
        d.target = dict(got["one"])
    elif got.get("several"):
        d.candidates, d.unmatched = list(got["several"]), list(got.get("unmatched") or [])


async def _next(d, lead: str = "") -> str:
    """Ask what is missing, what stops it, or the confirmation. Returns the line."""
    if not d.target:
        d.asked = _draft.WHO
        if d.candidates:
            names = ", ".join(c["name"] + (f" ({c['note']})" if c.get("note") else "") for c in d.candidates)
            if d.unmatched:
                return await _ask.line("send_ask_which_partial", lead, who=d.who, names=names,
                                       missing=" ".join(d.unmatched))
            return await _ask.line("send_ask_which", lead, who=d.who, names=names)
        if d.who and d.unread:
            return await _ask.line("send_cannot", lead, who=d.who, why="his contacts could not be read just now")
        return await (_ask.line("send_nobody", lead, who=d.who) if d.who else _ask.line("send_ask_who", lead))
    if not d.text:
        d.asked = _draft.TEXT
        return await _ask.line("send_ask_text", lead, who=d.target["name"])
    ok = await asyncio.to_thread(_deliver.check, d)
    if not ok.get("ok"):
        d.asked = _draft.WHO
        if ok.get("channels"):
            return await _ask.line("send_ask_channel", lead, who=d.target["name"],
                                   channels=", ".join(_ask.CHANNELS.get(c, c) for c in ok["channels"]))
        return await _ask.line("send_cannot", lead, who=d.target["name"], why=ok.get("why") or "")
    if ok.get("platform"):
        d.target["platform"] = ok["platform"]
    d.asked = _draft.CONFIRM
    d.confirm_line = await _ask.confirm(d.target["name"], d.target.get("platform") or d.channel, d.text)
    return d.confirm_line


def _apply(d, got: dict) -> None:
    if got.get("channel"):
        d.channel = got["channel"]
        if d.target:
            d.target["platform"] = got["channel"]
    if got.get("text") is not None:
        d.text = got["text"]
    if got.get("who") and got["who"] != (d.target or {}).get("name"):
        _resolve(d, got["who"])


async def _step(d, got: dict, last_line: str = "") -> str:
    """Apply one read to the draft and return what he hears."""
    if got.get("drop"):
        _draft.close(d, _draft.CANCELLED)
        _emit("dropped", d)
        return await _ask.line("send_not_sent")
    changed = got.get("text") is not None or bool(got.get("who")) or bool(got.get("channel"))
    _apply(d, got)
    if got.get("list") and not changed:
        names = _people.named(got["list"])
        _emit("listed", d, names=names)
        if not names:
            return await _ask.line("send_nobody", who=got["list"])
        d.asked = _draft.WHO
        if not d.target and len(names) > 1:
            d.candidates = list(_people.resolve(got["list"]).get("several") or d.candidates)
        return await _ask.line("send_listed", who=got["list"], names=", ".join(names))
    if got.get("send") and not changed and d.asked == _draft.CONFIRM and d.target and d.text:
        # A bare «yes» answers only the confirmation said LAST; after anything else in between he is read it again.
        if not got.get("bare") or " ".join(last_line.split()) == " ".join(d.confirm_line.split()):
            return await _send(d)
    lead = (f"Say back in a few words that the message now reads «{d.text}»." if got.get("text") is not None
            and d.text else "")
    return await _next(d, lead)


# ── the send ────────────────────────────────────────────────────────────────────────────────────────────────────────
def _run(d) -> dict:
    return _deliver.run(d)


async def _send(d) -> str:
    d.state = _draft.SENDING
    try:
        res = await asyncio.to_thread(_run, d)
    except Exception as e:  # noqa: BLE001
        res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    if not (isinstance(res, dict) and res.get("ok")):
        why = str((res or {}).get("message") or (res or {}).get("error") or "unknown")[:200]
        d.state, d.asked = _draft.OPEN, _draft.WHO        # his text stays: he decides what to do with it
        _emit("refused", d, why=why)
        return await _ask.line("send_cannot", who=d.target.get("name"), why=why)
    d.ref = _deliver.ref_of(res)
    _draft.close(d, _draft.SENT)
    _emit("queued", d, ref=d.ref)
    _receipt.follow_soon(d)
    return await _ask.line("send_going", who=d.target.get("name"))


# ── the two doors in ───────────────────────────────────────────────────────────────────────────────────────────────
def _orders_one(got: dict, by: str) -> bool:
    """Do his words order a message? A read that is only a «yes» (nobody named, nothing said) orders none."""
    if got.get("unread"):
        return by in SURE
    return bool(got.get("mine")) and not got.get("drop") and not (got.get("send") and not (got.get("who") or
                                                                                          got.get("text")))


async def intake(said: str, hint: dict | None = None, last_line: str = "", before: list[str] | None = None,
                 by: str = "call") -> str:
    """His order to send: a NEW draft, read from his words (the model's call fills what the read left empty). Returns
    the line the turn says: always a question — nothing leaves before his yes to the confirmation."""
    h = dict(hint or {})
    if (open_ := _draft.current()) is not None:
        if by == "worker":                       # a worker's message waits its turn behind the one he is writing
            n = _draft.queue(said, h, by)
            _emit("queued behind the open draft", open_, by=by, waiting=n)
            return ""
        # The gate's read of this sentence did not take it (not about the message, or unread): the same turn's call
        # or lean never replaces the message he is writing — the sentence is read again, with no clock, by the owner.
        taken, line = await take(said, last_line=last_line, before=before, bounded=False)
        _emit("kept the open draft", open_, by=by, said=str(said)[:200], taken=taken)
        return line if taken else ""
    d = _draft.start(said)
    d.by = by
    d.act, d.extra = _deliver.shape(h)
    # His words are read when he said them; a worker's act carries its fields and no words of his to read.
    got = dict(_read.NOTHING) if by == "worker" else await asyncio.to_thread(_read.read, said, d, last_line, before)
    if by != "worker" and not _orders_one(got, by):
        # Only HIS words order a message. A call, a verdict or a lean over words that do not («a bare yes», «stop
        # repeating me», «forget that message») opens nothing.
        _draft.close(d, _draft.CANCELLED)
        _emit("not a message", d, by=by, read=got)
        return ""
    who = got.get("who") or str(h.get("contact") or h.get("to") or "").strip()
    text = got.get("text") if got.get("text") is not None else (" ".join(str(h.get("text") or "").split()) or None)
    d.channel = got.get("channel") or str(h.get("channel") or h.get("platform") or "").strip().lower()
    if text:
        d.text = text
    if who:
        _resolve(d, who)
    elif d.act == "reply" or "n" in d.extra:   # a reply goes to the conversation it answers
        if (conv := _people.conversation(d.extra.get("n"))).get("name"):
            d.who, d.target = conv["name"], conv
    _emit("opened", d, by=by, read=got)
    return await _next(d)


async def take(said: str, *, last_line: str = "", before: list[str] | None = None,
               bounded: bool = True) -> tuple[bool, str]:
    """`(taken, line)`: one sentence of his while a draft is open. Not taken → the conversation's."""
    d = _draft.current()
    text = " ".join(str(said or "").split())
    if d is None or not text:
        return False, ""
    async with d.lock:                            # one sentence at a time: a split «yes» never sends twice
        if _draft.current() is not d:
            return True, ""                       # the sentence before this one already ended it, and said so
        t0 = time.monotonic()
        try:
            job = asyncio.to_thread(_read.read, text, d, last_line, before)
            got = await (asyncio.wait_for(job, _read.READ_S + 0.5) if bounded else job)
        except Exception as e:  # noqa: BLE001 — unread: the conversation's, never swallowed
            got = {**_read.NOTHING, "unread": True}
            _note(e)
        ms = round((time.monotonic() - t0) * 1000)
        if not got.get("mine"):
            _emit("unread" if got.get("unread") else "not mine", d, said=text[:200], ms=ms)
            return False, ""
        _draft.touch(d)
        line = await _step(d, got, last_line)
        _emit("taken", d, said=text[:200], read=got, ms=ms, line=line[:200])     # the draft as his words left it
    if _draft.current() is None:
        await _open_the_next()
    return True, line


async def _open_the_next() -> None:
    """The draft ended: the next message he asked for (or a worker handed over) is opened and asked out of turn."""
    nxt = _draft.next_queued()
    if nxt is None:
        return
    try:
        line = await intake(nxt["said"], nxt["hint"], by=nxt["by"] if nxt["by"] == "worker" else "call")
        if line:
            from nucleo.pulse import notices
            await notices.notify("zaelar", line, key=f"send:next:{abs(hash(line))}", kind="info")
    except Exception as e:  # noqa: BLE001
        _note(e)


def status() -> str:
    """One line about the open draft for the conversation's own context ("" when none): what is open and what it
    waits for — so a question about it is answered from the truth."""
    d = _draft.current()
    if d is None:
        return ""
    to = d.target.get("name") if d.target else (f"not chosen ({d.who})" if d.who else "nobody yet")
    wait = {"who": "who it is for", "text": "what it should say", "confirm": "his yes to send it"}.get(d.asked, "")
    return (f"A message is being written for him — to: {to}; text: «{d.text[:160]}»; waiting for {wait}. Not sent. "
            "Only his own words about it change or send it: you never send it, call its send, or say it is sent.")
