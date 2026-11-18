"""What the owner says: one FACT per moment, worded by a model (`nucleo/wording.py`), the language's own line the
example and the last resort — and the confirmation, which must carry his text verbatim.

The confirmation is the one line his yes answers, so it is checked after it is worded: it must name the person and
carry the whole text as it will leave; a wording that paraphrases or cuts either is replaced by the plain line.
"""
from __future__ import annotations

import unicodedata

#: «he» in a fact is the owner; the line is said TO him.
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
    "send_ask_channel": "The message for {who} can go by {channels}. Ask him which one.",
    "send_cannot": "The message for {who} cannot go as it is: {why}. Tell him plainly and ask him what to do.",
    "send_confirm": "The message for {who} ({channel}) reads EXACTLY: «{text}». Read him that text word for word, "
                    "inside quotes, name {who}, and ask whether to send it.",
    "send_confirm_later": "The message for {who} ({channel}) reads EXACTLY: «{text}», to be sent {when}. Read him that "
                          "text word for word, inside quotes, name {who}, say when it goes, and ask whether to send it.",
    "send_later": "The message to {who} is written and will be sent by itself {when}. Nothing has left yet.",
    "send_queued": "He asked for another message, to {who}. You will take it right after the one to {now}; say so in a "
                   "few words.",
    "send_listed": "The people in his contacts named «{who}» are: {names}. Tell him, and ask which one the message is "
                   "for.",
    "send_going": "He gave his go-ahead. The message to {who} is being sent right now — not confirmed yet.",
    "send_done": "The message to {who} has been SENT: the messaging service confirmed it went out.",
    "send_failed": "The message to {who} could NOT be sent. The reason: {why}.",
    "send_unconfirmed": "The message to {who} was handed over to be sent, but its confirmation has not arrived yet. He "
                        "will be told as soon as it does.",
    "send_not_sent": "He said not to send it. The message is NOT sent and nothing has left.",
}

CHANNELS = {"whatsapp": "WhatsApp", "telegram": "Telegram", "email": "email"}


def _plain(key: str, **fmt) -> str:
    from i18n import langs
    plain = str(getattr(langs.current_language(), key, "") or "")
    try:
        return plain.format(**fmt).strip()
    except Exception as e:  # noqa: BLE001 — a line whose blanks do not fit its language is no example
        from loguru import logger
        logger.debug(f"send.ask: «{key}» unfilled — {e!r}")
        return ""


async def line(key: str, lead: str = "", **fmt) -> str:
    """The line for `key`, worded from its fact; the language's own line when no model answers. `lead`: a fact said
    first, in the same line (what his words just changed)."""
    from nucleo import wording
    plain = _plain(key, **fmt)
    fact = FACTS[key].format(**{k: (str(v).strip() or "not given") for k, v in fmt.items()})
    if lead:
        fact = f"{lead} Then: {fact}"
    return await wording.word_soon(fact, examples=(plain,) if plain else (), fallback=plain) or plain


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or "").lower())
    return " ".join("".join(ch if ch.isalnum() else " " for ch in s if unicodedata.category(ch) != "Mn").split())


def carries(said: str, text: str, name: str, when: str = "") -> bool:
    """Does a worded confirmation carry the whole text, the person's whole name and (when it has one) its time?"""
    f = _fold(said)
    return all(bool(_fold(x)) and _fold(x) in f for x in (text, name)) and (not when or _fold(when) in f)


def when(ts: float) -> str:
    """A moment as he says it: the day and the hour («2026-11-19 09:00»), never a duration that ages."""
    import time
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(float(ts)))


async def confirm(name: str, platform: str, text: str, at: float = 0.0) -> str:
    """The ONE confirmation: worded, and verified to carry his text verbatim, her whole name and its time — else the
    plain line (a fixed one built from the same facts when the language has none)."""
    channel = CHANNELS.get(str(platform or "").lower(), str(platform or ""))
    key, at_s = ("send_confirm_later", when(at)) if at else ("send_confirm", "")
    said = await line(key, who=name, channel=channel, text=text, when=at_s)
    if carries(said, text, name, at_s):
        return said
    return _plain(key, who=name, channel=channel, text=text, when=at_s) or f"{name} · {channel} · «{text}» {at_s} ?"
