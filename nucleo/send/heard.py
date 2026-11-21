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
        d.heard, d.heard_at, d.heard_mono = True, now_ms(), time.monotonic()


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
        playing = False
        for e in observer.debug_events():
            if float(e.get("t_ms") or 0) < t_ms:
                continue
            label = str(e.get("label") or "")
            if (e.get("kind") == "vad" and (e.get("is_interruption") is True or e.get("resumed") is False)) \
                    or "barge-in" in label:
                return True
            if e.get("kind") == "state" and str(e.get("state") or label) == "speaking":
                playing = True                       # our voice started: the confirmation is being played
            elif e.get("kind") == "state" and str(e.get("state") or label) == "listening" and playing:
                return False                         # it played to the end with no voice of his over it
            elif e.get("kind") == "vad" and e.get("edge") == "on":
                return True                          # his voice began before the confirmation had played out
    except Exception as e:  # noqa: BLE001 — unreadable: as if cut, he is read it again
        _note(e)
        return True
    return False


def began_before(d) -> bool:
    """Did the sentence being read now BEGIN before the confirmation was said? Then it cannot be its answer, whatever it
    says («send it now» said while the draft was being built). A typed line has no onset of its own: never."""
    try:
        from voice import attention
        if attention.was_typed(within_s=10.0):
            return False
        from nucleo.input import typed
        on = typed.last_onset()
        return bool(on) and bool(d.heard_mono) and on < d.heard_mono
    except Exception as e:  # noqa: BLE001 — unreadable: as if it did, the confirmation is read again
        _note(e)
        return True


def answers(d, got: dict, last_line: str, *, changed: bool, ready: bool) -> tuple[bool, str]:
    """Does this read give his go-ahead to the confirmation open now? `(ok, why)`: every guard in ONE place, and the
    reason of each refusal (INI-042 #44 P0a — measured 2026-11-18: two «yes» re-asked with no trace of which guard).
    Only a confirmation he HEARD is answered; a bare «yes» answers only the one said LAST; never after another line of
    ours (a worker's «shall I send it?»), nor by a sentence begun before the confirmation existed. An act's bare yes
    answers its question only when said last, unless his words name again what it is about."""
    if not got.get("send"):
        return False, "the read did not take it as a go-ahead" + (" (a bare yes)" if got.get("bare") else "")
    if changed:
        return False, "his words also change the message"
    if not ready:
        return False, "nothing ready to send"
    said_last = _ask._fold(d.confirm_line) in _ask._fold(last_line)
    if not d.heard:
        return False, "he has not heard the confirmation"
    if d.kind == "act" and not (said_last or got.get("names") or not got.get("bare")):
        return False, "an act's bare yes, and its question was not our last line"
    if d.other_at > d.heard_at:
        return False, "another line of ours came after the confirmation"
    if began_before(d):
        return False, "his sentence began before the confirmation was said"
    if d.kind != "act" and got.get("bare") and not said_last:
        return False, "a bare yes, and the confirmation was not our last line"
    return True, ""
