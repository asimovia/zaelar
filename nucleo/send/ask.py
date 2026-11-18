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
    except Exception:  # noqa: BLE001
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


def carries(said: str, text: str, name: str) -> bool:
    """Does a worded confirmation carry the whole text and the person's first name?"""
    f = _fold(said)
    first = (_fold(name).split() or [""])[0]
    return bool(_fold(text)) and _fold(text) in f and (not first or first in f)


async def confirm(name: str, platform: str, text: str) -> str:
    """The ONE confirmation: worded, and verified to carry his text verbatim and her name — else the plain line."""
    channel = CHANNELS.get(str(platform or "").lower(), str(platform or ""))
    said = await line("send_confirm", who=name, channel=channel, text=text)
    return said if carries(said, text, name) else (_plain("send_confirm", who=name, channel=channel, text=text) or said)
