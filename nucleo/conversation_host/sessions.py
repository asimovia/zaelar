"""The registry of conversations (V2-941): ONE `Conversation` per account, in its own runtime, from when a session
switched on asks for it until the last one closes. A second session of the same account (the phone and the desktop)
joins the same conversation: one writer per account (I5). The runtime is started here and stopped here — nothing
else holds one.
"""
from __future__ import annotations

import threading
from typing import Any, Callable

from nucleo.conversation_host.runtime import ConversationRuntime

_lock = threading.Lock()
_live: dict[str, tuple[ConversationRuntime, set[str]]] = {}


def open_(account: str, session: str, make: Callable[[], Any], **runtime_kw) -> ConversationRuntime:
    """The account's runtime, started on its first session; this session joins it."""
    with _lock:
        got = _live.get(account)
        if got is None:
            got = (ConversationRuntime(make, **runtime_kw).start(), set())
            _live[account] = got
        got[1].add(session)
        return got[0]


def get(account: str) -> ConversationRuntime | None:
    with _lock:
        got = _live.get(account)
        return got[0] if got else None


def close(account: str, session: str) -> bool:
    """This session leaves; with the last one the runtime stops. True when it stopped."""
    with _lock:
        got = _live.get(account)
        if got is None:
            return False
        got[1].discard(session)
        if got[1]:
            return False
        del _live[account]
    got[0].stop()
    return True


def close_all() -> None:
    with _lock:
        runtimes = [rt for rt, _s in _live.values()]
        _live.clear()
    for rt in runtimes:
        rt.stop()
