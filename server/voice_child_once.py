"""A fact the voice process asked twice is replayed once (the body's door, V2-891).

The line from the voice process is at-least-once for the facts the body must not lose: a batch of events that is not
answered inside the sender's short timeout is asked ONCE more for his final words and the conversation items. A body
whose loop was held past that timeout HAS the batch, and answers late — so the second ask is the same fact again, and
it was replayed again: his sentence and the reply twice on the chat wall, about a second apart (measured 2026-11-19:
9 of 57 finals in one session, each beside a held loop, the reply's own item doubled in the same instant).

The identity is the sender's stamp: every event carries the instant it was queued (`at`), kept by the retry and by a
request that carried it and failed. The same kind, the same stamp and the same words are one fact. A sentence he says
twice on purpose is two stamps, so it is two facts — nothing here reads a clock or compares words alone.
"""
from __future__ import annotations

from collections import deque

from loguru import logger

_KEPT = 512
_ORDER: deque = deque()
_SEEN: set = set()
STATS = {"dropped": 0}


def _identity(ev):
    """The identity of a fact that may be asked twice — his final words, an item — or None for every other event."""
    if not isinstance(ev, dict) or ev.get("at") is None:
        return None
    k = ev.get("k")
    if k == "item" or (k == "transcript" and ev.get("final")):
        return (k, repr(ev.get("at")), str(ev.get("role") or ""), str(ev.get("text") or ""))
    return None


def once(events) -> list:
    """`events` without the facts this body already replayed. Order kept; everything unstamped passes."""
    out = []
    for ev in events or ():
        key = _identity(ev)
        if key is not None:
            if key in _SEEN:
                STATS["dropped"] += 1
                logger.debug(f"voice→body: {key[0]} asked twice, replayed once ({STATS['dropped']} so far)")
                continue
            _SEEN.add(key)
            _ORDER.append(key)
            if len(_ORDER) > _KEPT:
                _SEEN.discard(_ORDER.popleft())
        out.append(ev)
    return out


def forget() -> None:
    _ORDER.clear()
    _SEEN.clear()
    STATS["dropped"] = 0
