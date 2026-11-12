"""nucleo/turn/whisper — the whisperer: a typed slot filled BETWEEN turns, never a voice (V2-889 F2).

The old Susurro (removed in V2-851) was late, acted on a conversation that had moved on, bore tasks, pasted prose into
the next prompt and looped. This one cannot do any of that by construction: it starts only once a turn is CLOSED
(`turn_closed`, the last line of `pipeline_close.close_the_turn`), on its own thread; a deterministic gate decides
whether it is worth a call (`gate.py`); its output is a typed slot with no instruction field (`slot.py`); and in shadow
the slot is only measured — what it would render (`render.py`) is an event, wired into no prompt.
"""
from __future__ import annotations

import time

from loguru import logger

#: The bus topic a closed turn publishes (in-process; any reader may subscribe).
TOPIC = "turn.closed"


def turn_closed(*, brief=None, text: str = "", reply: str = "", started_at: float = 0.0) -> dict:
    """The turn is over: publish `turn.closed` and hand it to the whisperer. Never raises, never waits; returns {}."""
    try:
        from voice import trace
        payload = {"turn_id": trace.current(), "started_at": float(started_at or 0.0), "closed_at": time.time()}
        import bus
        bus.emit_sync(TOPIC, dict(payload))
        from nucleo.turn.whisper import run
        run.on_turn_closed({**payload, "brief": brief, "text": str(text or ""), "reply": str(reply or "")})
    except Exception as e:  # noqa: BLE001 — the turn is already over; its close never fails on this
        logger.debug(f"whisper: turn.closed not handed over — {e!r}")
    return {}
