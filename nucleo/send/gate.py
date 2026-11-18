"""The send at the turn's gate: a sentence about the open draft is the owner's, answered here in one line; anything
else goes on to the conversation untouched. Runs BEFORE the switchboard — a send is never a background process."""
from __future__ import annotations

import time

from loguru import logger


def _context(brain) -> tuple[str, list[str]]:
    """Our last line and his last two — what his sentence answers."""
    last, his = "", []
    try:
        last = str(getattr(brain, "_last_reply", "") or getattr(brain, "_last_spoken", "") or "")[:4000]
        for m in reversed(list(getattr(brain, "_window", None) or [])[-8:]):
            if m.get("role") == "user" and len(his) < 2:
                his.append(str(m.get("content") or "")[:200])
    except Exception as e:  # noqa: BLE001
        logger.debug(f"send.gate: context unread — {e!r}")
    return last, list(reversed(his))


def keep(brain, said: str, line: str, window_max: int = 0) -> None:
    """The exchange goes into the conversation's window, as any turn's does."""
    try:
        from nucleo.flash import dialog
        dialog.push_user(brain._window, said)
        if line:
            brain._window.append({"role": "assistant", "content": line})
            brain._last_spoken, brain._last_spoke_at = line, time.time()
            brain._last_reply = line
        if window_max:
            dialog.live_slice(brain._window, window_max)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"send.gate: window not kept — {e!r}")


async def at_the_gate(text: str, brain, say, motor=None) -> bool:
    """True when the open send took the sentence (and he was answered); False → the turn goes on."""
    from nucleo.send import draft, owner
    if draft.current() is None:
        return False
    last, before = _context(brain)
    try:
        taken, line = await owner.take(text, last_line=last, before=before)
    except Exception as e:  # noqa: BLE001 — a broken owner never eats his words: the conversation answers them
        logger.warning(f"send.gate: the owner failed on a sentence — {type(e).__name__}: {e}")
        return False
    if not taken:
        return False
    if brain is not None:
        keep(brain, text, line, getattr(motor, "_WINDOW_MAX", 0) if motor is not None else 0)
    if line and say is not None:
        try:
            say(line)
            owner.heard(line)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"send.gate: the line was not said — {e!r}")
    if motor is not None:
        try:
            motor._release_acc_trace_if_fresh(brain)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"send.gate: trace not released — {e!r}")
    return True
