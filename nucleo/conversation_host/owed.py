"""The `Owed` port of a switched session (V2-941, v3.1 §1.7, B6): what the engine owes the person lives in ONE ledger,
`notices` (`nucleo/pulse/notices.py`, its claim in `notice_claim.py`). While a session of the manager holds the voice, `notify` paints a line and
CLAIMS it for the voice — no push, no `shown` — and this port hands each claimed line to the manager once, which says
it as it is when it is free and nobody speaks. Said: `spoken`. Not: back to `owed`, for its other ways (the retry, a
push, the next screen). A claim past its deadline goes back by itself (the retry pulse). One consumer at a time.

`voice_live()` is the door `notify` asks; the voice session of the manager sets it (B8). Until then nothing is
claimed, and a notice goes its usual ways.
"""
from __future__ import annotations

import threading

from conversation.ports import OwedLine

_voice = {"live": False}
_handed: set[str] = set()
_lock = threading.Lock()


def voice_live() -> bool:
    return _voice["live"]


def set_voice_live(live: bool) -> None:
    _voice["live"] = bool(live)


class NoticesOwed:
    def next(self, account: str) -> OwedLine | None:
        from memory.api import notices as store
        with _lock:
            for r in store.claimed():
                key = r["dedupe_key"]
                if key not in _handed:
                    _handed.add(key)
                    return OwedLine(key, r.get("body") or "")
        return None

    def settle(self, key: str) -> None:
        from nucleo.pulse import notice_claim
        notice_claim.spoken(key)
        with _lock:
            _handed.discard(key)

    def release(self, key: str) -> None:
        from nucleo.pulse import notice_claim
        notice_claim.release(key)
        with _lock:
            _handed.discard(key)

    def owe(self, account: str, key: str, reason: str, *, voice: bool = True) -> None:
        """A run of the manager failed: the line that says so, in his language, through the one ledger, under the key
        the manager gave it (`conv:failed:<request>`): the claim and its `spoken` read the same key."""
        import asyncio

        from i18n import langs
        from nucleo.pulse import notices
        lines = getattr(langs.current_language(), "mute_lines", ()) or ()     # the pack's «I did not answer you»
        text = lines[0] if lines else "Sorry, I lost that. Could you say it again?"
        try:
            asyncio.get_running_loop().create_task(notices.notify("zaelar", text, key=key, speak=voice))
        except RuntimeError:
            asyncio.run(notices.notify("zaelar", text, key=key, speak=voice))
