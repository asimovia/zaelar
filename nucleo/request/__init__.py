"""nucleo/request/ — the Request is born once: its words, its row, what it is about (refactor2710-02).

The helpers its modules share live here once: `note` (a step that could not be read is said, never swallowed),
`base` (the card a widget or sheet id names), `acts_of` (the acts a retained question is about), `event` (one
`brain` event on the stream the caller holds, or the observer's) and `ends_asking` (a reply that closes on a question)."""
from __future__ import annotations

import sys

from loguru import logger


def note(e: BaseException) -> None:
    """A step that could not be read is said (debug), never swallowed: the module and the function that failed."""
    f = sys._getframe(1)
    logger.debug(f"{f.f_globals.get('__name__')}: {f.f_code.co_name} — {type(e).__name__}: {e}")


def base(wid) -> str:
    """The card a widget id names: a sheet's `card::id` is its card."""
    return str(wid or "").split("::", 1)[0].strip().lower()


def acts_of(retained: dict) -> list[str]:
    """The acts a retained question is about: the door's one act, or the card's leaving acts (`ask_outside_door.held`)."""
    return [str(a) for a in (retained.get("actions") or [retained.get("action")]) if a]


def event(emit, label: str, text: str, extra: dict) -> None:
    """One `brain` event on the stream the caller holds (`emit`), or the observer's when it holds none. Never raises."""
    try:
        if emit is None:
            from voice.observer import emit
        emit("brain", label, text=str(text or "")[:300], role="system", extra=extra)
    except Exception as e:  # noqa: BLE001
        note(e)


def ends_asking(reply: str) -> bool:
    """Does the reply close on a question? Its last mark — punctuation, never vocabulary."""
    last = str(reply or "").rstrip().rstrip("»\"'”)")[-1:]
    return bool(last) and last in "?？؟"
