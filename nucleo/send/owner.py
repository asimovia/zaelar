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
def _resolve(d, who: str, relation: str = "") -> None:
    """Point the draft at the person `who` names (among the candidates it was asking about, when it was); a relation
    he named her by («mum») reads the people he said are that."""
    was = list(d.candidates)
    got = _people.chosen(who, was, d.channel) if was else _people.resolve(who, d.channel, relation)
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
    if d.kind == "act":
        from nucleo.send import act as _act
        return await _act.next_step(d, lead)
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
    if not d.text and "attach_from" not in d.extra:      # a forward's files are its content
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
    d.asked, d.heard = _draft.CONFIRM, False
    files = int(d.extra.get("files_n") or 0)
    who = d.target["name"] + (f" ({d.target['note']})" if d.target.get("note") else "")   # a namesake, told apart
    d.confirm_line = await _ask.confirm(who, d.target.get("platform") or d.channel,
                                        d.text + (f" (📎×{files})" if files else ""), at=_deliver.at(d), lead=lead)
    return d.confirm_line


from nucleo.send import heard as _heard  # noqa: E402
from nucleo.send.heard import cut_since as _cut_since, heard  # noqa: E402,F401 — the mouth reports here


def _when(d, at: str) -> None:
    """A moment he said, read now (`now` drops one he gave before)."""
    if at.lower() == "now":
        d.extra.pop("at_ts", None)
        d.extra.pop("bad_time", None)
        return
    from widgets.mensajeria import held
    ts, bad = held.when({"at": at})
    d.extra.pop("bad_time", None)
    if bad:
        d.extra["bad_time"] = bad
    elif ts:
        d.extra["at_ts"] = ts


def _apply(d, got: dict) -> None:
    if got.get("at"):
        _when(d, got["at"])
    if got.get("channel"):
        d.channel = got["channel"]
        if d.target.get("chat_id") and d.target.get("platform") != d.channel:
            for k in ("reply_chat", "reply_to"):          # a chat lives on ONE platform: another channel is a new
                d.extra.pop(k, None)                      # message to the person, never this chat or this reply
            if d.target.get("contact_id"):
                d.target = {k: v for k, v in d.target.items() if k != "chat_id"}
                d.target["platform"] = got["channel"]
            else:
                _resolve(d, d.target.get("name") or d.who)
        elif d.target:
            d.target["platform"] = got["channel"]
    if got.get("text") is not None:
        d.text = got["text"]
    if got.get("who") and not _names_the_chosen(d, got["who"]):
        _resolve(d, got["who"])


def _names_the_chosen(d, who: str) -> bool:
    """«tell Raquel also…» while Raquel Ortega is chosen: words that are all in her name keep the choice."""
    if not d.target or d.target.get("note"):   # chosen among namesakes: the name alone no longer tells them apart
        return False
    said = set(_ask._fold(who).split())
    return bool(said) and said <= set(_ask._fold(d.target.get("name")).split())


async def _step(d, got: dict, last_line: str = "") -> str:
    """Apply one read to the draft and return what he hears."""
    if got.get("drop"):
        _draft.close(d, _draft.CANCELLED)
        _emit("dropped", d)
        if d.kind == "act":
            from nucleo.send import act as _act
            return await _act.line(d, "no")
        return await _ask.line("send_not_sent")
    if d.kind == "act":
        from nucleo.send import act as _act
        if _act.take_names(d, got.get("names") or []):   # other groups, other people: the same act, asked again
            d.heard, d.confirm_line, d.asked = False, "", ""
            _emit("act changed", d)
            return await _next(d)
    changed = (got.get("text") is not None or bool(got.get("channel")) or bool(got.get("at"))
               or bool(got.get("who") and not _names_the_chosen(d, got["who"])))
    if changed:                                   # the confirmation he heard was of another message: it no longer
        d.heard, d.confirm_line, d.asked = False, "", ""      # counts, from this instant, before anything awaits
    _apply(d, got)
    if got.get("list") and not changed:
        names = _people.named(got["list"])
        _emit("listed", d, names=names)
        if not names:
            return await _ask.line("send_nobody", who=got["list"])
        d.asked, d.unmatched = _draft.WHO, []
        if not d.target and len(names) > 1:
            d.candidates = list(_people.resolve(got["list"]).get("several") or d.candidates)
        return await _ask.line("send_listed", who=got["list"], names=", ".join(names))
    ready = d.kind == "act" or (d.target and (d.text or "attach_from" in d.extra))
    if got.get("send") and not changed and d.asked == _draft.CONFIRM and ready:
        # A bare «yes» answers only the confirmation said LAST; after anything else in between he is read it again.
        # Only a confirmation he HEARD is answered; a bare «yes» answers it only when it was said last.
        # …and never after another line of ours (a worker's «shall I send it?» is answered by his «yes, send it»), nor
        # by a sentence he began before the confirmation existed.
        if d.heard and d.other_at <= d.heard_at and not _heard.began_before(d) and (
                not got.get("bare") or _ask._fold(d.confirm_line) in _ask._fold(last_line)):
            return await _send(d)
    lead = (f"Say back in a few words that the message now reads «{d.text}»." if got.get("text") is not None
            and d.text else "")
    return await _next(d, lead)


# ── the send ────────────────────────────────────────────────────────────────────────────────────────────────────────
def _run(d) -> dict:
    if d.kind == "act":
        from nucleo.send import act as _act
        return _act.run(d)
    return _deliver.run(d)


from nucleo.send.go import send as _send  # noqa: E402,F401 — the act on his yes, its report (`go.py`)


# ── the two doors in ───────────────────────────────────────────────────────────────────────────────────────────────
async def intake(said: str, hint: dict | None = None, last_line: str = "", before: list[str] | None = None,
                 by: str = "call") -> str:
    """His order to send — `nucleo/send/intake.py`."""
    from nucleo.send import intake as _intake
    return await _intake.intake(said, hint, last_line, before, by)


async def take(said: str, *, last_line: str = "", before: list[str] | None = None,
               bounded: bool = True, superseded=None) -> tuple[bool, str]:
    """`(taken, line)`: one sentence of his while a draft is open. Not taken → the conversation's."""
    d = _draft.current()
    text = " ".join(str(said or "").split())
    if d is None or not text:
        return False, ""
    async with d.lock:                            # one sentence at a time: a split «yes» never sends twice
        if _draft.current() is not d:
            return False, ""                      # the sentence before ended it: this one is the conversation's
        if d.heard and _cut_since(d.heard_at):    # latched now, whoever this sentence turns out to be for
            d.heard = False
            _emit("confirmation cut", d)
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
        if superseded is not None and superseded():
            _emit("a fragment he went on from", d, said=text[:200])   # «yes…» of «yes… but take out the last
            return False, ""                                          # phrase»: the whole sentence is read, not this
        _draft.touch(d)
        line = await _step(d, got, last_line)
        _emit("taken", d, said=text[:200], read=got, ms=ms, line=line[:200])     # the draft as his words left it
    if _draft.current() is None:
        from nucleo.send import intake as _intake
        asyncio.ensure_future(_intake.open_the_next())    # never awaited here: an intake may be the caller
    return True, line


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
