"""A typed line that starts with `LOG:` is a note for whoever reads the timeline, not a turn.

Measured: the operator left notes for support inside his own session («LOG: the latency again…») and each one became
a turn — answered, routed, and once opened as an errand. There was no other way to write on the timeline from a
session: everything typed was his word to the agent.

The prefix is recognised at the typed door (`POST /api/chat`), case-insensitive, at the very start of the line
(`LOG:`, `log :`, `LOG:::` are the same). The note is recorded as one `feedback` event — the family the thumbs-down
already uses, so every viewer of the timeline shows it — and nothing else happens: no turn, no reply, no routing, no
errand, and no session is brought up for it.
"""
from __future__ import annotations

import re

#: `LOG` then one or more colons, at the start of the line, any case.
_PREFIX = re.compile(r"^\s*log\s*:+\s*", re.IGNORECASE)
#: How much of a note the timeline keeps.
MAX_CHARS = 2000


def body(text: str) -> str | None:
    """The note without its prefix, or None when the line is not a note (an ordinary turn)."""
    m = _PREFIX.match(str(text or ""))
    return None if m is None else str(text)[m.end():].strip()


def record(text: str, dev: str = "") -> bool:
    """Record the line if it is a note. True = it was a note and must not become a turn."""
    note = body(text)
    if note is None:
        return False
    try:
        from voice.observer import emit
        emit("feedback", "📝 support note (LOG:)", text=note[:MAX_CHARS], role="user",
             extra={"cat": "system", "support_note": True, **({"dev": dev} if dev else {})})
    except Exception:  # noqa: BLE001 — a note that cannot be traced is still not a turn
        pass
    return True
