"""The ear's facts from the voice process, on the body (V2-941, v3.1 §1.7, B8): the lossless lane's other end.

They arrive inside the body link's batches (`voice/engine/pipeline/body_link.py`, `send_ear`), numbered by the voice
process (`boot`, `seq`) and in order. A batch carried again because its answer came late applies nothing twice: each
`seq` is applied once, per boot. Each fact becomes the signal the package's ear reads (`ear_feed.py` made it, on one
wall clock) and is handed to the conversation in order (`entry.voice`). A declared hole (`gap`) is a `LinkGap` on
each device it covered: what the ear was hearing there ends incomplete, and is asked for again. At the end of one of
his turns the guards in front of the ear judge its words (`guards.py`): what they throw away reaches the ear as a
`Discard` before the end, and never closes as his words.
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
            _heard[str(ev.get("stream") or "")] = " ".join(str(w[0]) for w in ev.get("words") or ())
    out = gap + signals(ev)
    if ev.get("t") == "eot" and ev.get("kind") == "end":
        out = _guarded(ev) + out
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


def _guarded(ev: dict) -> list:
    """The guards in front of the ear, at the end of one of his turns: a `Discard` handed BEFORE the end, so what they
    threw away never closes as his words."""
    from nucleo.conversation_host import guards
    stream = str(ev.get("stream") or "")
    with _lock:
        text = _heard.pop(stream, "")
    why = guards.judge(text) if text.strip() else None
    if why:
        return [S.Discard(stream, text, why, int(ev.get("t_ms") or 0))]
    if text.strip() and guards.orders_stop(text):     # his spoken stop: the control first, then his words
        from nucleo.conversation_host import controls
        controls.control("stop", stream, "ear")
    return []


def _reset_for_tests() -> None:
    with _lock:
        _applied.clear()
        _turns.clear()
        _boot_of.clear()
        _heard.clear()
