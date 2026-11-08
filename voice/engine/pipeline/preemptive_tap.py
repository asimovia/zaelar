"""preemptive_tap.py — whether LiveKit's preemptive generation was USED or THROWN AWAY, on our timeline (V2-863).

`AgentSession` has run with `preemptive_generation.enabled` since it existed here, and nothing ever said what it did:
LiveKit starts the model on a transcript before the turn is confirmed, and at the end of the turn it either reuses
that speech («using preemptive generation») or discards it because the chat context or the tools changed in between.
Both decisions are one log line of `livekit.agents` each — and no `metrics_collected` event carries them, so in the 12
sessions measured on 2026-11-08 the first audio still landed ~2 s after the end of turn while the flag was on, and
nobody could say whether the early run had been wasted on every turn. This handler turns those two lines into one
`perf` event each, so the question has a number: how many turns the early run saved, and how many it cost for nothing.

It reads the SDK's own words (the two message prefixes below). An SDK upgrade that rewords them makes this blind, not
wrong: `test_preemptive_generation_is_measured.py` pins the prefixes against the installed `agent_activity.py`.
"""
from __future__ import annotations

import logging

USED_PREFIX = "using preemptive generation"
DISCARDED_PREFIX = "preemptive generation enabled but chat context or tools have changed"
LOGGER_NAME = "livekit.agents"

_installed: dict = {"handler": None}


class _Tap(logging.Handler):
    def __init__(self, emit):
        super().__init__(level=logging.DEBUG)
        self._emit = emit

    def emit(self, record: logging.LogRecord) -> None:  # noqa: A003 — logging's own name
        try:
            msg = str(record.getMessage() or "")
            if msg.startswith(USED_PREFIX):
                lead = getattr(record, "preemptive_lead_time", None)
                extra = {"cat": "system", "used": True}
                if isinstance(lead, (int, float)):
                    extra["lead_ms"] = round(float(lead) * 1000)
                self._emit("perf", "⚡ generación anticipada USADA", role="system", extra=extra)
            elif msg.startswith(DISCARDED_PREFIX):
                self._emit("perf", "✂️ generación anticipada DESCARTADA — el contexto o las tools cambiaron",
                           role="system", extra={"cat": "system", "used": False})
        except Exception:  # noqa: BLE001 — a tap never breaks the pipeline it watches
            pass


def install(emit) -> logging.Handler:
    """Attach the tap to LiveKit's logger once per process (idempotent: a second session reuses it)."""
    if _installed["handler"] is not None:
        return _installed["handler"]
    handler = _Tap(emit)
    lg = logging.getLogger(LOGGER_NAME)
    lg.addHandler(handler)
    # The two lines are DEBUG in the SDK; the logger must let them reach a handler without flooding the console
    # (the handler's own level is what filters — `setup_console_logging` keeps the stream handler at INFO).
    if lg.level == logging.NOTSET or lg.level > logging.DEBUG:
        lg.setLevel(logging.DEBUG)
    _installed["handler"] = handler
    return handler


def _reset_for_tests() -> None:
    h = _installed["handler"]
    if h is not None:
        logging.getLogger(LOGGER_NAME).removeHandler(h)
    _installed["handler"] = None
