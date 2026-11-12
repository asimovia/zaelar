"""nucleo/pulse/lk_marks.py — LiveKit's degraded-engine marks, read from the SDK's own log records.

Extracted from `homeostasis.py` (V2-891, the 300-line ceiling of a nucleo file): the heartbeat reads `_marks`, this
module fills it — from this process's `livekit` logger (embedded voice), or from the voice's OWN process, whose SDK
logs are its own and arrive at the body as events (`watch_into` there, `note_mark` here).
"""
from __future__ import annotations

import logging
import time

#: Degradation marks (timestamps), the window the heartbeat reads. Mutated in place, never rebound.
_marks: list[float] = []

_MARKERS = (
    "wait_pc_connection timed out",
    "entrypoint did not exit",
    # The job executor missed its health ping (a voice worker once went dead for hours after it). A blocked
    # thread can fire it transiently, so it counts in the same window+threshold and the same safety gate.
    "job executor is unresponsive",
)


def note_mark(at: float | None = None) -> None:
    """One degraded-engine mark — from this process's `livekit` logger, or from the voice's own process (V2-891),
    whose SDK logs are its own and reach the body as events."""
    _marks.append(float(at) if at else time.time())
    if len(_marks) > 256:                  # bound memory (a probe, not a history)
        del _marks[:128]


class _LKWatcher(logging.Handler):
    """Listens to the `livekit` logger (and children): stamps a mark on each degraded-engine message. Emits nothing.
    `sink` is where the mark goes (`note_mark` here; the voice process hands it to the body)."""

    def __init__(self, sink=None) -> None:
        super().__init__()
        self._sink = sink

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            msg = record.getMessage().lower()
        except Exception:
            return
        if any(m in msg for m in _MARKERS):
            (self._sink or note_mark)(time.time())


def watch_into(sink) -> logging.Handler:
    """The voice process's half (V2-891): its `livekit` marks go to `sink(at)` instead of this process's window."""
    h = _LKWatcher(sink)
    h.setLevel(logging.WARNING)
    logging.getLogger("livekit").addHandler(h)
    return h


_watcher = _LKWatcher()
_watcher.setLevel(logging.WARNING)
