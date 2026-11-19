"""The cold-turn attention judge started on the EAGER end of turn (operator 2026-11-19, cloud speed (iii)).

Measured on a cloud test Machine: a COLD turn (after the conversation window lapsed) paid the judge — one model call,
~1.0-1.25 s — in series after the ear confirmed the turn and before the prompt. `prefire` starts it on the words the ear
ANNOUNCED (`nucleo/turn/brief_turn.fire_early`), so it runs while the ear confirms the turn. It decides nothing:
`attention.evaluate_content` still awaits a verdict before anything acts, and takes this one only for the SAME words
judged with the SAME frame (`prefired`); otherwise it judges as always.
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger

#: The judge started on the EAGER end of turn (`prefire`): `{"key": (text, context), "at": epoch s, "task": Task}`.
_PREFIRE: dict = {}
PREFIRE_TTL_S = 20.0


def _last_said() -> str:
    """What the assistant last said, as the timeline has it (the frame the gate will most likely judge with)."""
    try:
        from voice import observer
        for e in reversed(observer.debug_events("transcript", limit=40)):
            if e.get("role") == "assistant" and str(e.get("text") or "").strip():
                return str(e.get("text") or "")
    except Exception as e:  # noqa: BLE001 — no frame read: nothing is prefired, the gate judges as always
        logger.debug(f"attention.prefire: last line unread — {e!r}")
    return ""


def prefire(text: str, now: float | None = None) -> None:
    """Start the cold-turn judge on the words the ear ANNOUNCED (the eager end of turn), so its ~1 s runs while the
    ear confirms the turn instead of after it (operator 2026-11-19, cloud speed (iii)). It decides nothing: the gate
    still awaits a verdict before anything acts, and reuses this one only for the SAME words judged with the SAME
    frame (`prefired`); otherwise it judges as always. A warm turn, a wake word or another mode start nothing."""
    t = (text or "").strip()
    now = time.time() if now is None else now
    from voice import attention as a
    if not t or a.mode() != "always" or a.has_wakeword(t) or a.window_warm(now):
        return
    ctx = _last_said()
    if not ctx.strip() or _PREFIRE.get("key") == (t, ctx):
        return
    try:
        task = asyncio.get_running_loop().create_task(a._directed_judge(t, ctx))
    except RuntimeError as e:                             # no loop here: the gate judges as always
        return logger.debug(f"attention.prefire: no running loop, not prefired — {e!r}")
    old = _PREFIRE.get("task")
    if old is not None and not old.done():
        old.cancel()
    _PREFIRE.update({"key": (t, ctx), "at": now, "task": task})


def prefired(text: str, context: str):
    """The prefired judgement for exactly these words, once, when the frame it was judged with ENDS in the gate's frame
    (`_last_reply`): the timeline's line carries the spoken lead-in («Ya voy… ») the reply does not. None otherwise."""
    said, ctx = _PREFIRE.get("key") or ("", ""), str(context or "").strip()
    if said[0] != text or not ctx or not str(said[1]).rstrip().endswith(ctx) or time.time() - float(_PREFIRE.get("at") or 0) > PREFIRE_TTL_S:
        return None
    task = _PREFIRE.pop("task", None)
    _PREFIRE.clear()
    return task


def clear() -> None:
    _PREFIRE.clear()
