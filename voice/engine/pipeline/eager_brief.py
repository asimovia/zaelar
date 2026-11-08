"""eager_brief.py — the turn's brief fires when the ear ANNOUNCES the end of turn, not when it confirms it (V2-863).

Deepgram Flux emits an `EagerEndOfTurn` before its `EndOfTurn`; the LiveKit plugin forwards it as a
`PREFLIGHT_TRANSCRIPT`, and the session starts the model on it (preemptive generation). The brief — the one Jev call of
the turn (`nucleo/turn/brief.py`), 250 ms p50 measured on 2026-11-08 — used to fire only at ADMISSION, so the pool of the
lead-in cover was chosen by regex and Jev's verdict could only swap it at the last instant. Fired here, on the same
words the model is about to read, it has landed by the time the turn is armed (`filler_audio.arm` → `settle_brief`),
so the cover is decided from the verdict BEFORE the model is paid.

This wrapper sees the raw STT events (`Agent.stt_node`); it changes none of them. A preflight whose words then GROW
(he resumed) is a different sentence: the admitted turn fires its own brief, as today — `brief_turn.prefired` matches
by the words as said, not by the event.
"""
from __future__ import annotations

from loguru import logger


def _text_of(ev) -> str:
    try:
        alts = getattr(ev, "alternatives", None) or []
        return str(getattr(alts[0], "text", "") or "").strip() if alts else ""
    except Exception:  # noqa: BLE001
        return ""


def on_preflight(text: str) -> None:
    """One eager end of turn: fire the brief on it and leave a mark on the timeline."""
    if not text:
        return
    try:
        from voice.observer import emit
        emit("vad", "⚡ fin de turno ANTICIPADO — el brief sale ya", text=text[:160], role="system",
             extra={"cat": "system", "detector": "stt-eager"})
    except Exception:  # noqa: BLE001
        pass
    try:
        from nucleo.turn import brief_turn as _bt
        _bt.fire_early(text)
    except Exception as e:  # noqa: BLE001 — a classifier may never break the ear
        logger.debug(f"eager brief: not fired — {e!r}")


async def stt_node_firing_the_brief(agent, default_impl, audio, model_settings):
    """`Agent.stt_node` with one ear on the preflight events. Every event passes through untouched."""
    from livekit.agents import stt as _stt
    out = default_impl(agent, audio, model_settings)
    if hasattr(out, "__await__") and not hasattr(out, "__aiter__"):
        out = await out
    if out is None:
        return
    async for ev in out:
        try:
            if getattr(ev, "type", None) == _stt.SpeechEventType.PREFLIGHT_TRANSCRIPT:
                on_preflight(_text_of(ev))
        except Exception as e:  # noqa: BLE001
            logger.debug(f"eager brief: event unread — {e!r}")
        yield ev
