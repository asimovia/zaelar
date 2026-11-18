"""The owner of a send: intake, every sentence about it, the one question, the send on his yes, the receipt.

`intake(said, hint)` — the turn hands over his words (and the model's call as a hint). Returns the line the turn says.
`take(said, …)` — at the turn's gate, before anything else routes his words: True when the sentence was about the open
send (answered here, at once); False when it is not (the conversation answers it). Never swallows what it cannot read.

What happens next is decided here and nowhere else, by code over the draft:
  · nobody resolved → resolve the name (`people`): one → chosen; several → ask which, naming them; nobody → ask who;
  · no text → ask what to tell her;
  · both → ask ONE confirmation naming who, how and the text;
  · his go-ahead with both → send, through the card's own act with the person's row id, and follow it to the
    connector's receipt; the final line is the receipt's.
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger

from nucleo.send import draft as _draft
from nucleo.send import people as _people
from nucleo.send import read as _read
from nucleo.send import receipt as _receipt

#: The hand-over that only LEANS to a message (an order on the messaging card, no message act read): when the owner's
#: read says his words are not a message, the turn goes on as any other. Every other hand-over that the read refuses
#: is DROPPED — no other lane may act on a message.
LEAN = "order"

#: The FACT behind each line (worded by `nucleo/wording.py`), keyed by the language's own line — its example and its
#: last resort. «he» in a fact is the owner; the line is said TO him.
FACTS = {
    "send_ask_who": "He wants to send a message but has not said to whom. Ask him who it is for.",
    "send_nobody": "He wants to send a message to «{who}», but nobody in his contacts has that name. Say so and ask "
                   "him who it is for.",
    "send_ask_which": "He wants to send a message to «{who}», and several people in his contacts could be meant: "
                      "{names}. Ask him which one, naming them.",
    "send_ask_which_partial": "He wants to send a message to «{who}». Nobody in his contacts is called that — nobody "
                              "has «{missing}» in their name. The people it could be: {names}. Say so plainly and "
                              "ask him which one, naming them.",
    "send_ask_text": "He wants to send a message to {who}. Ask him what you should tell {who}.",
    "send_confirm": "The message for {who} ({channel}) reads: «{text}». Read him the text and ask whether to send it.",
    "send_listed": "The people in his contacts named «{who}» are: {names}. Tell him, and ask which one the message is "
                   "for.",
    "send_going": "He gave his go-ahead. The message to {who} is being sent right now — not confirmed yet.",
    "send_done": "The message to {who} has been SENT: the messaging service confirmed it went out.",
    "send_failed": "The message to {who} could NOT be sent. The reason: {why}.",
    "send_unconfirmed": "The message to {who} was handed over to be sent, but its confirmation has not arrived yet. He "
                        "will be told as soon as it does.",
    "send_not_sent": "He said not to send it. The message is NOT sent and nothing has left.",
}


def _note(e: Exception) -> None:
    logger.debug(f"send.owner: {type(e).__name__}: {e}")


def _emit(label: str, d, **extra) -> None:
    try:
        from voice.observer import emit
        emit("send", f"📨 send · {label}", text=(d.text if d else "")[:200], role="system",
             extra={"cat": "flash", "event": "send", "step": label, **({"draft": d.snapshot()} if d else {}), **extra})
    except Exception as e:  # noqa: BLE001 — the record never decides the send
        _note(e)


async def _line(key: str, lead: str = "", **fmt) -> str:
    """The line for `key`, worded from its fact; the language's own line when no model answers. `lead`: a fact said
    first, in the same line (what his words just changed)."""
    from i18n import langs
    from nucleo import wording
    plain = str(getattr(langs.current_language(), key, "") or "")
    try:
        plain = plain.format(**fmt).strip()
    except Exception:  # noqa: BLE001
        plain = ""
    fact = FACTS[key].format(**{k: (str(v).strip() or "not given") for k, v in fmt.items()})
    if lead:
        fact = f"{lead} Then: {fact}"
    return await wording.word_soon(fact, examples=(plain,) if plain else (), fallback=plain) or plain


def _channel_name(d) -> str:
    p = str(d.target.get("platform") or d.channel or "")
    return {"whatsapp": "WhatsApp", "telegram": "Telegram", "email": "email"}.get(p, p or "his usual channel")


# ── the next step, by code ──────────────────────────────────────────────────────────────────────────────────────────
def _resolve(d, who: str) -> None:
    """Point the draft at the person `who` names (among the candidates it was asking about, when it was)."""
    d.who, d.target, was = who, {}, list(d.candidates)
    got = _people.chosen(who, was, d.channel) if was else _people.resolve(who, d.channel)
    d.candidates, d.unmatched = [], []
    if got.get("one"):
        d.target = dict(got["one"])
    elif got.get("several"):
        d.candidates, d.unmatched = list(got["several"]), list(got.get("unmatched") or [])


async def _next(d, lead: str = "") -> str:
    """Ask what is missing, or the confirmation. Returns the line."""
    return await (_missing(d, lead) if not (d.target and d.text) else _confirm(d))   # the confirmation reads the text


async def _confirm(d) -> str:
    d.asked = _draft.CONFIRM
    return await _line("send_confirm", who=d.target["name"], channel=_channel_name(d), text=d.text)


async def _missing(d, lead: str = "") -> str:
    """The question for what the draft still lacks: who it is for, else what it says."""
    if not d.target:
        if d.candidates:
            d.asked = _draft.WHO
            names = ", ".join(c["name"] + (f" ({c['note']})" if c.get("note") else "") for c in d.candidates)
            if d.unmatched:
                return await _line("send_ask_which_partial", lead, who=d.who, names=names, missing=" ".join(d.unmatched))
            return await _line("send_ask_which", lead, who=d.who, names=names)
        d.asked = _draft.WHO
        return await (_line("send_nobody", lead, who=d.who) if d.who else _line("send_ask_who", lead))
    d.asked = _draft.TEXT
    return await _line("send_ask_text", lead, who=d.target["name"])


def _apply(d, got: dict) -> None:
    if got.get("channel"):
        d.channel = got["channel"]
        if d.target:
            d.target["platform"] = got["channel"]
    if got.get("text") is not None:
        d.text = got["text"]
    if got.get("who") and got["who"] != (d.target or {}).get("name"):
        _resolve(d, got["who"])


async def _step(d, got: dict) -> str:
    """Apply one read to the draft and return what he hears."""
    if got.get("drop"):
        _draft.close(d, _draft.CANCELLED)
        _emit("dropped", d)
        return await _line("send_not_sent")
    changed = got.get("text") is not None or bool(got.get("who")) or bool(got.get("channel"))
    _apply(d, got)
    if got.get("list") and not changed:
        names = _people.named(got["list"])
        _emit("listed", d, names=names)
        if not names:
            return await _line("send_nobody", who=got["list"])
        d.asked = _draft.WHO
        if not d.target and len(names) > 1:
            d.candidates = [c for c in _people.resolve(got["list"]).get("several") or []]
        return await _line("send_listed", who=got["list"], names=", ".join(names))
    if got.get("send") and not changed and d.asked == _draft.CONFIRM and d.target and d.text:
        return await _send(d)
    lead = (f"Say back in a few words that the message now reads «{d.text}»." if got.get("text") is not None
            and d.text else "")
    return await _next(d, lead)


# ── the send and its receipt ────────────────────────────────────────────────────────────────────────────────────────
def _payload(d) -> dict:
    p = {"text": d.text, "contact": d.target.get("name") or d.who}
    if d.target.get("contact_id"):
        p["contact_id"] = d.target["contact_id"]
    elif d.target.get("chat_id"):
        p["chat_id"] = d.target["chat_id"]          # a conversation with no contact row: that chat by its id
    if d.target.get("platform") or d.channel:
        p["channel"] = d.target.get("platform") or d.channel
    return p


def _run(payload: dict) -> dict:
    from widgets.mensajeria import data as _md
    return _md.apply_action("send_to", payload)


async def _send(d) -> str:
    d.state = _draft.SENDING
    try:
        res = await asyncio.to_thread(_run, _payload(d))
    except Exception as e:  # noqa: BLE001
        res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    if not (isinstance(res, dict) and res.get("ok")):
        why = str((res or {}).get("error") or (res or {}).get("message") or "unknown")[:200]
        _draft.close(d, _draft.FAILED)
        _emit("refused", d, why=why)
        return await _line("send_failed", who=d.target.get("name"), why=why)
    from nucleo.request import send_receipt
    d.ref = send_receipt._ref_of(res)
    _draft.close(d, _draft.SENT)
    _emit("queued", d, ref=d.ref)
    _receipt.follow_soon(d)
    return await _line("send_going", who=d.target.get("name"))


# ── the two doors in ───────────────────────────────────────────────────────────────────────────────────────────────
async def intake(said: str, hint: dict | None = None, last_line: str = "", before: list[str] | None = None,
                 by: str = "call") -> str:
    """His order to send: a NEW draft, read from his words (the model's call fills what the read left empty). Returns
    the line the turn says — a question, or «sending» when his order itself was the go-ahead over a complete draft."""
    h = hint or {}
    if by != "worker" and (open_ := _draft.current()) is not None:
        # The gate already read this sentence against the open draft and found it is not about the message: a call or
        # a lean of the same turn does not get to replace the message he is writing (measured 2026-11-18: «stop
        # repeating what I say» → the model called the send, and the draft waiting for his yes became «to whom?»).
        _emit("kept the open draft", open_, by=by, said=str(said)[:200])
        return ""
    d = _draft.start(said)
    # His words are read when he said them; a worker's act carries its fields and no words of his to read.
    got = dict(_read.NOTHING) if by == "worker" else await asyncio.to_thread(_read.read, said, d, last_line, before)
    who = got.get("who") or str(h.get("contact") or h.get("to") or "").strip()
    text = got.get("text") if got.get("text") is not None else (" ".join(str(h.get("text") or "").split()) or None)
    d.channel = got.get("channel") or str(h.get("channel") or h.get("platform") or "").strip().lower()
    if text:
        d.text = text
    if who:
        _resolve(d, who)
    elif "n" in h or not d.target:      # a reply, or a message with nobody named: the conversation it answers / he has open
        if (conv := _people.conversation(h.get("n"))).get("name"):
            d.who, d.target = conv["name"], conv
    if by != "worker" and not (got.get("mine") and not got.get("drop") and (got.get("who") or got.get("text"))):
        # Only HIS words order a message: they name who or say what. A call, a verdict or a lean over words that do not
        # («a bare yes», «stop repeating me», «forget that message») opens nothing.
        _draft.close(d, _draft.CANCELLED)
        _emit("not a message", d, by=by, read=got)
        return ""
    _emit("opened", d, by=by, read=got)
    # His order may carry the go-ahead itself («send it now»): then a complete draft leaves without a second question.
    if got.get("send") and d.target and d.text:
        d.asked = _draft.CONFIRM
        return await _send(d)
    return await _next(d)


async def take(said: str, *, last_line: str = "", before: list[str] | None = None) -> tuple[bool, str]:
    """`(taken, line)`: one sentence of his while a draft is open. Not taken → the conversation's."""
    d = _draft.current()
    text = " ".join(str(said or "").split())
    if d is None or not text:
        return False, ""
    t0 = time.monotonic()
    try:
        got = await asyncio.wait_for(asyncio.to_thread(_read.read, text, d, last_line, before), _read.READ_S + 0.5)
    except Exception as e:  # noqa: BLE001 — unread: the conversation's, never swallowed
        _emit("unread", d, said=text[:200], why=f"{type(e).__name__}")
        return False, ""
    ms = round((time.monotonic() - t0) * 1000)
    if not got.get("mine"):
        _emit("not mine", d, said=text[:200], ms=ms)
        return False, ""
    _draft.touch(d)
    line = await _step(d, got)
    _emit("taken", d, said=text[:200], read=got, ms=ms, line=line[:200])     # the draft as his words left it
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
