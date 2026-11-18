"""The ONE state of a send: what he asked to send, to whom, and what was last asked him about it.

There is at most one open draft. A new send replaces it; a draft nobody touches for `IDLE_S` is closed silently, so
an abandoned one never owns a sentence of his.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field

#: A draft he has not spoken about for this long is closed: it no longer reads his sentences.
IDLE_S = 600.0

#: What the owner last asked him (`asked`).
WHO, TEXT, CONFIRM = "who", "text", "confirm"
#: Where a draft stands (`state`).
OPEN, SENDING, SENT, FAILED, CANCELLED = "open", "sending", "sent", "failed", "cancelled"


@dataclass
class Draft:
    said: str                                   # his words that opened it
    who: str = ""                               # the name as he said it (or as he chose it)
    channel: str = ""                           # a platform he named, "" for the person's own
    text: str = ""                              # the message as it will be written
    target: dict = field(default_factory=dict)  # {name, contact_id, platform} once resolved to ONE person
    candidates: list = field(default_factory=list)   # [{name, contact_id, note}] when several could be meant
    unmatched: list = field(default_factory=list)    # the words he said that none of them carries
    asked: str = ""
    state: str = OPEN
    ref: str = ""                               # the outbox order once queued
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    opened_at: float = field(default_factory=time.time)
    touched_at: float = field(default_factory=time.time)

    def snapshot(self) -> dict:
        d = asdict(self)
        d["text"] = d["text"][:300]
        return d


_open: dict = {"draft": None}


def current() -> Draft | None:
    """The open draft, or None (an idle one is closed here)."""
    d = _open["draft"]
    if d is None:
        return None
    if d.state != OPEN or time.time() - d.touched_at > IDLE_S:
        _open["draft"] = None
        return None
    return d


def start(said: str) -> Draft:
    d = Draft(said=" ".join(str(said or "").split()))
    _open["draft"] = d
    return d


def close(d: Draft, state: str) -> None:
    d.state = state
    if _open["draft"] is d:
        _open["draft"] = None


def touch(d: Draft) -> None:
    d.touched_at = time.time()


def reset() -> None:
    """Forget the open draft (tests, a hard reset)."""
    _open["draft"] = None
