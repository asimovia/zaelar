"""voice/reply_text.py — a model's reply made fit to be said: no sentence or block of words said twice in a row, no
stage directions (INI-078 F2 step 8, T3: moved out of the old turn's `nucleo/flash/dialog.py`, which keeps the window).

Deterministic and idempotent: normal text comes back as it went in. Read by whatever has a model reply to say — the
cluster's composer among them.
"""
from __future__ import annotations

import re
import unicodedata


def norm(s: str) -> str:
    """Accents, case and punctuation aside: the form two sentences are compared in."""
    n = unicodedata.normalize("NFKD", s or "")
    n = "".join(c for c in n if not unicodedata.combining(c)).lower()
    return re.sub(r"[^0-9a-z ]+", " ", n).strip()


def collapse_repeated_phrase(text: str, max_block: int = 10) -> str:
    """A contiguous block of words said twice becomes one («let me check let me check» → «let me check»), the largest
    block first, until nothing changes."""
    for _ in range(4):
        toks = text.split()
        n = len(toks)
        out: list[str] = []
        i = 0
        changed = False
        while i < n:
            hit = False
            for size in range(min(max_block, (n - i) // 2), 0, -1):
                if [w.lower() for w in toks[i:i + size]] == [w.lower() for w in toks[i + size:i + 2 * size]]:
                    out.extend(toks[i:i + size])
                    i += 2 * size
                    hit = changed = True
                    break
            if not hit:
                out.append(toks[i])
                i += 1
        text = " ".join(out)
        if not changed:
            break
    return text


def sanitize_reply(text: str) -> str:
    """A small model's reply under repetition, made sayable: a sentence said twice in a row once, a repeated block of
    words once, its stage directions out (`speech.drop_stage_directions`)."""
    if not text or not text.strip():
        return text
    parts = re.split(r"(?<=[.!?…])\s+", text.strip())
    dedup: list[str] = []
    for p in parts:
        if dedup and norm(p) and norm(p) == norm(dedup[-1]):
            continue
        dedup.append(p)
    from voice import speech
    t = speech.drop_stage_directions(collapse_repeated_phrase(" ".join(dedup)))
    return re.sub(r"\s+", " ", t).strip()
