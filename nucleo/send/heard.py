"""Whether he HEARD the confirmation: the mouth that says a line reports it (`heard`), and his voice over ours after it
(`cut_since`) takes it back — handed to the mouth is not heard."""
from __future__ import annotations

import time

from loguru import logger

from nucleo.send import ask as _ask
from nucleo.send import draft as _draft


def _note(e: Exception) -> None:
    logger.debug(f"send.heard: {type(e).__name__}: {e}")


def heard(line: str, spoken: bool = True) -> None:
    """The mouth that said `line` reports it: when it is the open draft's confirmation, he has now HEARD it — the one
    thing a go-ahead can answer."""
    d = _draft.current()
    if d is not None and spoken and line and d.confirm_line and _ask._fold(line).endswith(_ask._fold(d.confirm_line)):
        if _talking():
            return                   # said while HE is talking: it plays under his voice — not heard, read again
        d.heard, d.heard_at = True, now_ms()


def _talking() -> bool:
    try:
        from nucleo.input import typed
        return typed.speaking()
    except Exception as e:  # noqa: BLE001 — unreadable: as if he were talking, it is read again
        _note(e)
        return True


def now_ms() -> float:
    try:
        from voice import observer
        return float(observer.now_ms())
    except Exception as e:  # noqa: BLE001
        _note(e)
        return time.time() * 1000.0


def cut_since(t_ms: float) -> bool:
    """Did his voice cut ours after `t_ms` — an overlap read as an interruption, a turn cancelled by his barge-in, or
    a cut speech that did not resume? Then what was being said may not have reached him."""
    try:
        from voice import observer
        for e in observer.debug_events():
            if float(e.get("t_ms") or 0) < t_ms:
                continue
            label = str(e.get("label") or "")
            if (e.get("kind") == "vad" and (e.get("is_interruption") is True or e.get("resumed") is False)) \
                    or "barge-in" in label:
                return True
    except Exception as e:  # noqa: BLE001 — unreadable: as if cut, he is read it again
        _note(e)
        return True
    return False
