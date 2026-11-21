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
#: How an open draft ended with no state of its own: nobody touched it (`IDLE_S`), or a new send took its place.
IDLE, REPLACED = "idle", "replaced"


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
    kind: str = "message"                       # "message", or "act": a group created or left (`nucleo/send/act`)
    widget: str = "mensajeria"                  # the card whose act it is
    extra: dict = field(default_factory=dict)   # that act's other fields (a reply's `n`, files, a subject, a time)
    confirm_line: str = ""                      # the confirmation he was read, exactly — his bare yes answers only it
    heard: bool = False                         # that confirmation was SAID to him (not only written)
    heard_at: float = 0.0                       # when it was handed to the mouth (ms on the observer's clock)
    other_at: float = 0.0                       # when another line of ours was said after it
    heard_mono: float = 0.0                     # the same instant on the ear's clock (`nucleo/input/typed`)
    by: str = ""                                # who handed it over (the model's call, a verdict, a worker)
    box_key: str = ""                           # its view in its card: the box the owner painted it in (`send/card`)
    trace: str = ""                             # the flow of the order that opened it: every step of it is seen there
    unread: bool = False                        # his contacts could not be read when the name was looked up
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False, compare=False)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    opened_at: float = field(default_factory=time.time)
    touched_at: float = field(default_factory=time.time)

    def names_said(self) -> list[str]:
        """What an act is about as it stands: the items of its declared list field (groups, members)."""
        for v in (self.extra or {}).values():
            if isinstance(v, list) and all(isinstance(x, str) for x in v):
                return list(v)
        return [str(self.extra.get(k)) for k in ("group", "name") if str((self.extra or {}).get(k) or "").strip()][:1]

    def snapshot(self) -> dict:
        keys = ("id", "said", "who", "channel", "text", "target", "candidates", "unmatched", "asked", "state", "ref",
                "act", "kind", "widget", "by")
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
        _open["draft"] = None                 # the messages queued behind an idle one keep their own clock
        if d.state == OPEN:
            _ended(d, IDLE)                   # an idle draft ends where it is seen, never silently
        return None
    return d if d.state == OPEN else None     # while it SENDS it is not current, and is not let go either


def start(said: str) -> Draft:
    from voice import trace
    old = _open["draft"]
    d = Draft(said=" ".join(str(said or "").split()), trace=trace.current())
    _open["draft"] = d
    if old is not None and old.state == OPEN:
        _ended(old, REPLACED)
    return d


def close(d: Draft, state: str) -> None:
    d.state = state
    if _open["draft"] is d and state != OPEN:
        _open["draft"] = None
    if state in (SENT, FAILED, CANCELLED):
        _ended(d, state)


#: Who is told when a draft ends (`on_end`): its view in its card (`send/card.install`).
_on_end: list = []


def on_end(fn) -> None:
    if fn not in _on_end:
        _on_end.append(fn)


def _ended(d: Draft, state: str) -> None:
    """The ONE point a draft ends — sent, failed, cancelled, idle or replaced: each listener is told, none can stop it."""
    for fn in list(_on_end):
        try:
            fn(d, state)
        except Exception as e:  # noqa: BLE001 — a listener that fails never keeps a draft open
            __import__("loguru").logger.debug(f"send.draft: an end listener failed ({e!r})")


def touch(d: Draft) -> None:
    d.touched_at = time.time()


def reset() -> None:
    """Forget the open draft and the queued ones (tests, a hard reset)."""
    _open["draft"] = None
    _queue.clear()


def queue(said: str, hint: dict, by: str) -> int:
    """Keep a message he asked for while another is open; returns how many wait."""
    _queue.append({"said": said, "hint": dict(hint or {}), "by": by, "at": time.time()})
    return len(_queue)


def next_queued() -> dict | None:
    """The oldest message still waiting; one that waited longer than a draft lives is gone (never opened stale)."""
    while _queue:
        q = _queue.pop(0)
        if time.time() - float(q.get("at") or 0) <= IDLE_S:
            return q
    return None
