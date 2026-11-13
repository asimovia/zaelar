"""Which TURN a brief belongs to, and the brief asked before its turn (refactor2710-07, from `nucleo/turn/brief.py`).

A verdict about a card is re-validated when it is consumed (`owner_still_open`): the brief enumerates what was open at
fire time, and two seconds later a card may have closed. A brief is joined to its turn by trace (`of_this_turn`) for the
readers no caller hands it to. And a decision that must be taken BEFORE the model — a hard stop that may name an
activity — fires the brief early (`verdict_before_the_turn`); the turn that admits the same sentence reuses it.
"""
from __future__ import annotations

from loguru import logger

#: Briefs fired for a sentence before its turn was admitted — a hard stop that asks first, or the EAGER end of turn the
#: ear announces (V2-863) — keyed by the sentence as spoken: `{key: (at, handle)}`. The turn that then admits the SAME
#: sentence reuses it instead of paying a second round trip. Bounded: an eager that never became a turn ages out.
_PREFIRED: dict = {}
PREFIRED_TTL_S = 8.0
_PREFIRED_MAX = 4


def _key(text: str) -> str:
    """The sentence as SAID: case, punctuation and spacing are the transcriber's, not his (an eager transcript and the
    confirmed one differ by a full stop and a capital when he did not resume)."""
    import re
    import unicodedata
    t = unicodedata.normalize("NFKD", str(text or "")).casefold()
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(re.findall(r"[^\W_]+", t))


def prefired(operator_text: str):
    """The handle fired early for this very sentence, once, while fresh — else None."""
    import time
    key = _key(operator_text)
    pre = _PREFIRED.pop(key, None) if key else None
    if pre and time.time() - pre[0] <= PREFIRED_TTL_S and pre[1]:
        return pre[1]
    return None


def _remember_prefired(operator_text: str, handle) -> None:
    import time
    key = _key(operator_text)
    if not key or not handle:
        return
    _PREFIRED[key] = (time.time(), handle)
    while len(_PREFIRED) > _PREFIRED_MAX:
        _PREFIRED.pop(next(iter(_PREFIRED)))


def fire_early(operator_text: str):
    """Fire the turn's brief on a sentence the ear has HEARD but not yet confirmed (the eager end of turn, V2-863), and
    keep it for the turn that admits the same words. Nobody waits here. A sentence already fired is not fired twice;
    a sentence that grows (he resumed) is a new sentence and gets its own brief — the verdict judges the words the
    model reads. Returns the handle, or None (Jev off, empty words, a failure — the turn fires its own at admission)."""
    key = _key(operator_text)
    if not key:
        return None
    import time
    have = _PREFIRED.get(key)
    if have and time.time() - have[0] <= PREFIRED_TTL_S and have[1]:
        return have[1]
    try:
        from nucleo.turn import brief
        handle = brief.ask_for_turn(operator_text)
    except Exception as e:  # noqa: BLE001 — a classifier may never break a turn
        logger.debug(f"brief: the eager brief did not fire — {e!r}")
        return None
    _remember_prefired(operator_text, handle)
    return handle


async def verdict_before_the_turn(operator_text: str, key: str, *, wait_s: float = 2.0):
    """Fire the turn's brief NOW, before the turn is admitted, and wait up to `wait_s` for one key: `(choice, info)`.
    The handle is kept for the turn that admits the same sentence (`ask_for_turn`). For a decision that must be taken
    before the model and is a judgement about the sentence (a hard stop that may name an activity), never a word table."""
    import asyncio
    import time
    from nucleo.turn import brief
    handle = brief.ask_for_turn(operator_text)
    if not handle:
        return None, None
    _remember_prefired(operator_text, handle)
    try:
        await asyncio.to_thread(handle["event"].wait, wait_s)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"brief: the early verdict was not awaited — {e!r}")
    from nucleo.turn import verdicts
    return verdicts.read(handle, key, None)


def judged_text(handle, fallback: str = "") -> str:
    """The sentence this brief's verdicts were asked about, or `fallback` (V2-820 T-06): a guard that reads the turn's
    words must read the same words the verdict did."""
    got = handle.get("judged") if isinstance(handle, dict) else None
    return str(got) if got else (fallback or "")


def stamp(handle, *, turn_id=None, open_ids=None):
    """Record WHICH turn this brief belongs to and WHAT was open when it was asked (a join, not a guess by time)."""
    if isinstance(handle, dict):
        handle["turn_id"] = turn_id
        handle["open_ids"] = [str(w) for w in (open_ids or [])]
        remember_for_the_turn(handle)
        try:     # the errand portal is reached from many callers and none hands it the brief: the trace joins them
            from nucleo.flash import capability_gap as _gap_d
            from voice import trace as _trace
            _gap_d.remember(handle, _trace.current())
        except Exception as e:  # noqa: BLE001 — without it the portal judges nothing, which is today's path
            logger.debug(f"brief: capability verdict not joinable to the trace: {e!r}")
    return handle


#: The turn's brief by trace, for readers no caller hands it to (a canvas close, the errand portal). Bounded.
_BY_TRACE: dict = {}


def remember_for_the_turn(handle) -> None:
    try:
        from voice import trace as _trace
        if (t := _trace.current()):
            _BY_TRACE[t] = handle
            while len(_BY_TRACE) > 32:
                _BY_TRACE.pop(next(iter(_BY_TRACE)))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"brief: not joinable to the trace — {e!r}")


def of_this_turn():
    """The brief of the turn running now (by its trace), or None."""
    try:
        from voice import trace as _trace
        return _BY_TRACE.get(_trace.current() or "")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"brief: no trace for this turn — {e!r}")
        return None


def owner_still_open(handle, widget_id: str) -> bool:
    """Is the card a verdict names STILL on screen? `True` when the brief carried no open set (fail-soft)."""
    known = (handle or {}).get("open_ids") if isinstance(handle, dict) else None
    if not known:
        return True
    wid = (widget_id or "").strip().lower()
    if wid in {str(w).strip().lower() for w in known}:
        try:
            from memory import api as _memapi
            now = {str(w).strip().lower() for w in ((_memapi.state() or {}).get("open_widgets") or [])}
        except Exception:  # noqa: BLE001
            return True
        if not now:
            return True
        return wid in now     # an INSTANCE that closed while its base stayed open is a stale verdict too


