"""The ear's facts from the voice process, on the body (V2-941, v3.1 §1.7, B8): the lossless lane's other end.

They arrive inside the body link's batches (`voice/engine/pipeline/body_link.py`, `send_ear`), numbered by the voice
process (`boot`, `seq`) and in order. A batch carried again because its answer came late applies nothing twice: each
`seq` is applied once, per boot. Each fact becomes the signal the package's ear reads (`ear_feed.py` made it, on one
wall clock) and is handed to the conversation in order (`entry.voice`). A declared hole (`gap`) is a `LinkGap` on
each device it covered: what the ear was hearing there ends incomplete, and is asked for again. At the end of one of
his turns a stop is a control and a `Discard` before the end; the other guards the ear asks at every close
(`guards.for_ear`), with the turn's first word as the echo's timing (`rose_of`). His voice and our playback feed the
body's attention (`_attend`), where those guards judge.
"""
from __future__ import annotations

import threading

from conversation.ear import signals as S

_lock = threading.Lock()
_applied: dict[str, int] = {}                     # boot → the last seq applied
_turns: dict[tuple, int] = {}                     # (stream, boot, epoch, provider turn) → the ear's own turn number
_boot_of: dict[str, str] = {}                     # stream → the voice process's boot its facts came from
_next = {"turn": 0}
TURNS_KEPT = 4096
_heard: dict[str, str] = {}                       # stream → the words of the turn in course, for the guards
_rose: dict[str, float] = {}                      # stream → when its first word began (wall ms): the echo's timing
_rose_turn: dict[str, object] = {}                # stream → the turn `_rose` belongs to


def signals(ev: dict) -> list:
    """One fact → the ear's signals (a fixed translation; an unknown kind is none)."""
    t, s = ev.get("t"), str(ev.get("stream") or "")
    if t == "words":
        words = tuple((str(w[0]), int(w[1]), int(w[2]), float(w[3])) for w in ev.get("words") or ())
        window = tuple(int(x) for x in (ev.get("window") or (0, 0)))
        return [S.WordSpan(s, int(ev.get("turn") or 0), int(ev.get("rev") or 0), bool(ev.get("final")), words,
                           (window[0], window[1]))]
    if t == "eot":
        prob = ev.get("prob")
        return [S.EotHint(s, "flux", str(ev.get("kind") or ""), float(prob) if isinstance(prob, (int, float)) else None,
                          int(ev.get("t_ms") or 0), ev.get("terminal") if isinstance(ev.get("terminal"), bool) else None)]
    if t == "mark":
        return [S.Watermark(s, int(ev.get("through") or 0))]
    if t == "vad":
        return [S.VadEdge(s, str(ev.get("edge") or ""), int(ev.get("t_ms") or 0), bool(ev.get("echo_safe", True)))]
    if t == "playback":
        return [S.PlaybackState(s, bool(ev.get("speaking")), int(ev.get("t_ms") or 0))]
    if t == "gap":
        return [S.LinkGap(str(stream), int(ev.get("t_ms") or 0)) for stream in ev.get("streams") or () if stream]
    return []


def fresh(ev: dict) -> bool:
    """Is this `seq` new for its boot (and so applied now)? A repeated one is not."""
    boot, seq = str(ev.get("boot") or ""), int(ev.get("seq") or 0)
    with _lock:
        if seq <= _applied.get(boot, 0):
            return False
        _applied[boot] = seq
        return True


def receive(ev: dict, hand=None) -> int:
    """Apply one fact once, in order. Returns how many signals were handed over."""
    if not fresh(ev):
        return 0
    if hand is None:
        from nucleo.conversation_host import entry
        hand = entry.voice
    gap = _new_boot(ev)
    if ev.get("t") == "words":
        ev = {**ev, "turn": _turn_of(ev)}
        with _lock:
            stream = str(ev.get("stream") or "")
            _heard[stream] = " ".join(str(w[0]) for w in ev.get("words") or ())
            starts = [float(w[1]) for w in ev.get("words") or () if len(w) > 1]
            if _rose_turn.get(stream) != ev["turn"]:          # a new turn of his: its own first word
                _rose.pop(stream, None)
                _rose_turn[stream] = ev["turn"]
            if starts:
                _rose[stream] = min(starts + ([_rose[stream]] if stream in _rose else []))
    out = gap + signals(ev)
    _attend(ev)
    if ev.get("t") == "eot" and ev.get("kind") == "end":
        out = _stopped(ev) + out
    for sig in out:
        hand(sig)
    return len(out)


def _turn_of(ev: dict) -> int:
    """The ear's own number for a provider turn: the provider numbers turns from 0 in every stream, so its number is
    unique only with the stream's epoch and the voice process's boot."""
    key = (str(ev.get("stream") or ""), str(ev.get("boot") or ""), int(ev.get("epoch") or 0), int(ev.get("turn") or 0))
    with _lock:
        if key not in _turns:
            if len(_turns) >= TURNS_KEPT:
                _turns.pop(next(iter(_turns)))
            _next["turn"] += 1
            _turns[key] = _next["turn"]
        return _turns[key]


def _new_boot(ev: dict) -> list:
    """A voice process that started again: what the ear was hearing from the one before ends incomplete (a gap)."""
    stream, boot = str(ev.get("stream") or ""), str(ev.get("boot") or "")
    if not stream or not boot:
        return []
    with _lock:
        before = _boot_of.get(stream)
        _boot_of[stream] = boot
    return [S.LinkGap(stream, int(ev.get("t_ms") or ev.get("through") or 0))] if before and before != boot else []


def _attend(ev: dict) -> None:
    """The attention guard is judged HERE, in the body, so the body's attention hears what the voice process hears: his
    voice rising and falling, our own voice sounding. Its window then measures his silence from his last word and
    from the end of our reply — never from one turn's end to the next across the model and our whole line."""
    from voice import attention
    t, at = ev.get("t"), float(ev.get("t_ms") or 0) / 1000 or None
    if t == "vad" and ev.get("edge") == "rise":
        attention.note_speech_onset(at)
    elif t == "vad" and ev.get("edge") == "fall":
        attention.note_speech_end(at)
    elif t == "playback":
        attention.note_bot_speech(bool(ev.get("speaking")), at)


def _stopped(ev: dict) -> list:
    """At the end of one of his turns: is it his stop? Then a control, and the turn a `Discard` (`stop`) handed BEFORE
    the end — never words for the model. The other guards are the ear's to ask, at every close (`guards.for_ear`)."""
    from nucleo.conversation_host import guards
    stream = str(ev.get("stream") or "")
    with _lock:
        text = _heard.pop(stream, "")
    if text.strip() and guards.orders_stop(text):     # his spoken stop is a CONTROL, never words for the model:
        from nucleo.conversation_host import controls  # the control, and the turn is discarded as `stop`
        from voice import attention
        controls.control("stop", stream, "ear")
        attention.close_window("voice-order")         # «cállate» closes the conversation's window as well
        return [S.Discard(stream, text, "stop", int(ev.get("t_ms") or 0))]
    return []


def rose_of(stream: str) -> float | None:
    """When the turn of his in course on `stream` began (its first word, wall ms): the echo guard's timing."""
    with _lock:
        return _rose.get(str(stream or ""))


def _reset_for_tests() -> None:
    with _lock:
        _applied.clear()
        _turns.clear()
        _boot_of.clear()
        _heard.clear()
        _rose.clear()
        _rose_turn.clear()
