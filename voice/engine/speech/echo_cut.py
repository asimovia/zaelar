"""The cover's echo, cut from the head of the reply — deterministic, zero tokens (V2-864, CRIT-V4c).

The node in `filler_audio.py` sounds a short cover («Look…», «Un segundo…») before the model's reply, and the model
is told which phrase sounded. Measured on a real voice session, the model still opened 4 of 7 covered replies with
the very words of the cover («Look…» → «Look, you're right…»): a model echoes its lead-in, and a sentence in its
prompt does not stop it. `EchoCut` does. The reply's first words are held until there are enough of them to compare,
and when they ARE the cover (word for word, however punctuated or accented) they are dropped together with the
punctuation that followed, and the next word is capitalised. Anything else passes untouched, so a reply that merely
CONTINUES the cover («…you told me to close it») is never cut. One decision per turn; after it, every chunk passes
straight through.
"""
from __future__ import annotations

import logging
import string
import unicodedata

_LEAD = string.whitespace + ",.;:…—–-"     # what may sit between the echoed cover and the reply's own first word
_ENDS = ".!?\n"                             # a sentence mark ends the head early


def _spans(text: str) -> list[tuple[int, int]]:
    """Where each word of `text` starts and ends: a run of letters or digits (the underscore is not a word)."""
    out, start = [], None
    for i, c in enumerate(text):
        if c.isalnum():
            if start is None:
                start = i
        elif start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(text)))
    return out


def words(text: str) -> list[str]:
    """The words of a phrase as SAID: case, accents and punctuation («Look…», «Look,») are the voice's, not the model's."""
    t = unicodedata.normalize("NFKD", str(text or "")).casefold()
    t = "".join(c for c in t if not unicodedata.combining(c))
    return [t[a:b] for a, b in _spans(t)]


def first_word(phrase: str) -> str:
    """The cover's first word exactly as it sounds, capital included («Un segundo…» → «Un»)."""
    s = _spans(str(phrase or ""))
    return phrase[s[0][0]:s[0][1]] if s else ""


class EchoCut:
    """Cuts the cover the model REPEATS at the head of its reply; see the module docstring."""

    def __init__(self, phrase: str):
        self._phrase = phrase
        self._cover = words(phrase)
        self._buf = ""
        self._last = None
        self._decided = not self._cover
        self.cut = False

    def _need(self) -> bool:
        # Enough words to compare: the cover's own count plus one more word started (so «Look» vs «Looking» cannot
        # be confused), or a sentence mark that ends the head early.
        return len(words(self._buf)) > len(self._cover) or any(c in _ENDS for c in self._buf)

    def _decide(self) -> str:
        self._decided = True
        if words(self._buf)[:len(self._cover)] != self._cover:
            return self._buf
        # Walk past the cover's words in the ORIGINAL text, then the punctuation and spaces that followed it.
        pos = _spans(self._buf)[len(self._cover) - 1][1]
        rest = self._buf[pos:].lstrip(_LEAD)
        self.cut = True
        return rest[:1].upper() + rest[1:] if rest else ""

    def feed(self, text: str) -> str:
        """Text to emit NOW for this chunk ("" while the head is still being held)."""
        if self._decided:
            return text
        self._buf += str(text or "")
        return self._decide() if self._need() else ""

    def flush(self) -> str:
        """The stream ended: whatever is held is decided with what there is."""
        return "" if self._decided else self._decide()

    def pass_chunk(self, chunk) -> list:
        """What to yield for one model chunk: a chunk with no text (a tool call, a usage report) untouched, text
        through the cut."""
        text = chunk_text(chunk)
        if text is None:
            return [chunk]
        self._last = chunk
        out = self.feed(text)
        return [with_text(chunk, out)] if out else []

    def close(self) -> list:
        """The stream ended: what was still held, and ONE event when the echo was cut."""
        tail = self.flush()
        if self.cut:
            _note_cut(self._phrase)
        return [with_text(self._last, tail)] if tail and self._last is not None else []


def chunk_text(chunk) -> str | None:
    """The text of a model chunk, or None when it carries none (a tool call, a usage report)."""
    if isinstance(chunk, str):
        return chunk
    content = getattr(getattr(chunk, "delta", None), "content", None)
    return content if isinstance(content, str) else None


def with_text(chunk, text: str):
    """The same chunk carrying `text` instead of its own."""
    if isinstance(chunk, str):
        return text
    chunk.delta.content = text
    return chunk


def _note_cut(phrase: str) -> None:
    """One event per cut: the chat wall and the timeline show that the model repeated its cover and the voice did not."""
    try:
        from voice.observer import emit
        emit("brain", "✂️ eco de la cobertura recortado", text=phrase, role="system",
             extra={"cat": "flash", "path": "segment"})
    except Exception as e:  # noqa: BLE001 — the reply already sounded; a lost mark must not break the stream
        logging.getLogger(__name__).warning("echo-cut mark not written: %s", e)
