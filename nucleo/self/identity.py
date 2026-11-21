"""The assistant's own name and how it listens: the doors that change them, and the fact the memory reads (CRIT-V8).

A rename is the structured fact `state.assistant_name` (the wake word follows it, `voice.attention.set_assistant_name`);
the listening mode is the configured setting `attention_mode`. Both change only by the model's own act
(`rename_yourself`, `set_attention` in the conversation host, `acts_self.py`), with the name as its declared argument —
never words pulled out of his sentence.

The memory processor distils facts off the conversation and may read an `assistant.name` atom; it writes one only
when he ordered THAT rename a moment ago (`rename_heard`): a search term or a quoted name never renames the assistant
(V2-752: «He dicho, Apollo once»). Fails closed.
"""
from __future__ import annotations

import asyncio
import re
import time
import unicodedata

#: The rename he last ordered, never consumed: the memory processor reads it to decide whether an `assistant.name`
#: atom it distilled is a rename HE ordered.
_HEARD: dict = {"name": "", "at": 0.0}
#: How long after the act the memory processor may still read it: the processor runs off the conversation, seconds later.
HEARD_S = 600.0
#: The longest name kept.
NAME_MAX = 32


def apply_rename_now(name: str) -> None:
    """Process-level: the session's wake word tracks the new name at once, before the durable write."""
    from voice import attention
    attention.set_assistant_name(name)


async def persist_rename(name: str) -> None:
    from memory import api as _mem
    await asyncio.to_thread(_mem.set_state, {"assistant_name": name})


async def persist_attention_mode(mode_val: str) -> None:
    from config import settings as _cfg
    await asyncio.to_thread(_cfg.update, {"attention_mode": mode_val})


def ordered(name: str, *, now: float | None = None) -> None:
    """He ordered the assistant to be called `name` (the model's act, with its declared argument)."""
    _HEARD.update(name=str(name or "").strip()[:NAME_MAX], at=time.time() if now is None else now)


def rename_heard(value: str, *, now: float | None = None) -> bool:
    """Did he order a rename in the last `HEARD_S` — to this name? The read the memory processor makes before it writes
    `assistant.name`. No order, an old one or another name → False: fails closed."""
    t = time.time() if now is None else now
    if not _HEARD["at"] or t - _HEARD["at"] > HEARD_S:
        return False
    said = " ".join(str(_HEARD["name"] or "").lower().split())
    return not said or said == " ".join(str(value or "").lower().split())


def sentences_with(name: str, text: str) -> list[str]:
    """The sentences of `text` that carry `name` (whole word, any case), each on its own — [] when none does."""
    n = (name or "").strip()
    if not n:
        return []
    # Sentence-final punctuation of every script the packs speak (`。！？` CJK, `؟` Arabic, `।` Devanagari), no word
    # of any language: a script with no space after its full stop still ends a sentence there.
    parts = [p.strip() for p in re.split(r"(?<=[.!?¡¿;\n])\s+|(?<=[。！？؟।])\s*|\n+", str(text or "")) if p.strip()]
    return [p for p in parts if _names(n, p)]


def _script(ch: str) -> str:
    return (unicodedata.name(ch, "").split() or [""])[0] if ch.isalpha() else ""


def _names(name: str, sentence: str) -> bool:
    """`name` stands as a word in `sentence`: no letter OF ITS OWN SCRIPT touches it. «是Johnny。» names Johnny — CJK
    puts no space between words — and «Johnnyboy» does not."""
    for m in re.finditer(re.escape(name), sentence, re.I):
        before = sentence[m.start() - 1] if m.start() else ""
        after = sentence[m.end()] if m.end() < len(sentence) else ""
        if _script(before) != _script(name[0]) and _script(after) != _script(name[-1]):
            return True
    return False
