"""The `Telemetry` port of a switched session (V2-941, the F1 plan §4.7): every event of the manager goes to the
engine's observer — the visor, the session log, the Master — as `observer.emit(kind, label, extra=payload)`. This
module and `conversation/telemetry.py` are RELAYS on the architecture map, so the piece an event is stamped with is
the package module that emitted it. It also tells the waiters of the typed doors (`entry.py`) when their request
closed.
"""
from __future__ import annotations


class ObserverTelemetry:
    def __init__(self, listeners: tuple = ()) -> None:
        self._listeners = listeners

    def emit(self, kind: str, label: str, payload: dict) -> None:
        for listen in self._listeners:
            listen(kind, label, payload)
        try:
            from voice import observer
            observer.emit(kind, label, extra=payload)
        except Exception as e:  # noqa: BLE001 — the port never raises; the manager goes on and counts it
            __import__("logging").getLogger("zaelar.conversation_host").debug(f"telemetry: {kind}/{label}: {e!r}")
