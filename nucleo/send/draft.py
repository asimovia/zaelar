"""The ONE state of a send: what he asked to send, to whom, and what was last asked him about it.

There is at most one open draft. A new send replaces it; a draft nobody touches for `IDLE_S` is closed silently, so
an abandoned one never owns a sentence of his.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field

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
    act: str = "send_to"                        # the card's act that will carry it (send_to · reply · forward)
    extra: dict = field(default_factory=dict)   # that act's other fields (a reply's `n`, files, a subject, a time)
    confirm_line: str = ""                      # the confirmation he was read, exactly — his bare yes answers only it
    heard: bool = False                         # that confirmation was SAID to him (not only written)
    by: str = ""                                # who handed it over (the model's call, a verdict, a worker)
    unread: bool = False                        # his contacts could not be read when the name was looked up
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False, compare=False)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    opened_at: float = field(default_factory=time.time)
    touched_at: float = field(default_factory=time.time)

    def snapshot(self) -> dict:
        keys = ("id", "said", "who", "channel", "text", "target", "candidates", "unmatched", "asked", "state", "ref",
                "act", "by")
        d = {k: getattr(self, k) for k in keys}
        d["text"] = d["text"][:300]
        return d


_open: dict = {"draft": None}
#: The messages he asked for while another was open, in order: each is opened when the one before it ends.
_queue: list = []


def current() -> Draft | None:
    """The open draft, or None (an idle one is closed here)."""
    d = _open["draft"]
    if d is None:
        return None
    if time.time() - d.touched_at > IDLE_S or d.state in (SENT, FAILED, CANCELLED):
        _open["draft"] = None                 # an idle draft takes the messages queued behind it with it
        if d.state == OPEN:
            _queue.clear()
        return None
    return d if d.state == OPEN else None     # while it SENDS it is not current, and is not let go either


def start(said: str) -> Draft:
    d = Draft(said=" ".join(str(said or "").split()))
    _open["draft"] = d
    return d


def close(d: Draft, state: str) -> None:
    d.state = state
    if _open["draft"] is d and state != OPEN:
        _open["draft"] = None


def touch(d: Draft) -> None:
    d.touched_at = time.time()


def reset() -> None:
    """Forget the open draft and the queued ones (tests, a hard reset)."""
    _open["draft"] = None
    _queue.clear()


def queue(said: str, hint: dict, by: str) -> int:
    """Keep a message he asked for while another is open; returns how many wait."""
    _queue.append({"said": said, "hint": dict(hint or {}), "by": by})
    return len(_queue)


def next_queued() -> dict | None:
    return _queue.pop(0) if _queue else None
