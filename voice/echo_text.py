"""Is what the ear heard our own line coming back? (V2-941, v3.1 B10b — the voice pass: our TTS fed into the microphone
cut our line and entered as his words.)

Echo is decided by TIMING first — his voice rose while our line sounded, or right after it ended — and then by
CONTAINMENT: the words heard are, in order, words of that line. Never by the similarity of the whole line: a few words
heard back from a long line are a small part of it. Characters only (case folded, letters and digits kept), no word
table, so it holds in any language.
"""
from __future__ import annotations

#: the share of the heard words that must be found, in order, in our line to call them our own
SHARE = 0.7
#: fewer heard words than this tell nothing yet: a single word is in most lines
MIN_WORDS = 2


def tokens(text) -> list[str]:
    """`text` (or a list of words) as folded tokens: letters and digits, the rest a separator."""
    raw = " ".join(text) if isinstance(text, (list, tuple)) else str(text or "")
    return "".join(c.casefold() if c.isalnum() else " " for c in raw).split()


def contained(heard, line) -> bool:
    """The heard words are, in order, words of `line` (at least `SHARE` of them, and at least `MIN_WORDS`)."""
    h, s = tokens(heard), tokens(line)
    if len(h) < MIN_WORDS or not s:
        return False
    i = found = 0
    for w in h:
        j = i
        while j < len(s) and s[j] != w:
            j += 1
        if j < len(s):
            found, i = found + 1, j + 1
    return found >= SHARE * len(h)
