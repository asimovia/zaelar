"""The guards in front of the ear (V2-941, v3.1 §1.7 and §1.6 bis, B10): speech they throw away never reaches the
conversation as his words — the ear gets a `Discard` with its reason (I4: the text and the reason are kept).

Judged once, when the provider ends a turn of his (`eot end`), over the words of that turn, in this order:
  · `mic_blocked` — his microphone is closed (or the engine stopped): closed is not an opinion (`mic_input`);
  · `echo` — the words are our own last line heard back through his microphone, within the echo window;
  · `not_addressed` — the attention mode says it was not said to us (`attention.evaluate`, pure; a directed turn keeps
    the conversation's window warm, an ambient one is noted).
The voice lock needs no guard here: the voice process hears only the room of the session that holds the voice.
"""
from __future__ import annotations

import os
import time

_last: dict = {"text": "", "at": 0.0}


def said(text: str, at: float | None = None) -> None:
    """Our line as it goes out on the voice (`voice_mouth`): what the echo guard compares against."""
    _last.update(text=str(text or ""), at=time.time() if at is None else at)


def orders_stop(text: str) -> bool:
    """Does his turn order a stop? The engine's own detector (`attention.is_shut_up`): the package reads no words."""
    from voice import attention
    return attention.is_shut_up(text)


def judge(text: str, now: float | None = None) -> str | None:
    """Why this turn of his is thrown away, or None when it goes to the conversation."""
    from voice import attention, mic_input
    now = time.time() if now is None else now
    if mic_input.blocks_turn(text):
        return "mic_blocked"
    if _last["text"] and now - _last["at"] < float(os.getenv("ZAELAR_ECHO_WINDOW_S", "12")):
        from nucleo.flash import dialog
        if dialog.similar(text, _last["text"], thr=0.82):
            return "echo"
    verdict = attention.evaluate(text, now=now)
    if not verdict.directed:
        attention.note_ambient(text, now=now)
        return "not_addressed"
    attention.note_directed(now=now)
    return None
