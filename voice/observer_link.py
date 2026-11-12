"""voice/observer_link.py — the observer's line to the body, in the voice's OWN process (V2-891).

There the voice records nothing itself: every event goes to the body, which owns the record, the SSE stream and the
database both surfaces read (`voice/engine/pipeline/body_link.py` carries it). The event's `piece` is read HERE, while
the module that emitted it is still on the stack — this file is a relay of the stream in the architecture map, so the
walk (`observability/pieces.emitter`) passes over it. `FORWARD["fn"]` unset = the local record (the body, a test).
"""
from __future__ import annotations

from loguru import logger

FORWARD: dict = {"fn": None}


def forward_to(fn) -> None:
    """`fn(event_dict)` receives every event instead of the local record; None restores the local record."""
    FORWARD["fn"] = fn


def forward(kind, label, text, role, extra, piece):
    from voice.observer import _stamp_piece
    ev = {"kind": kind, "label": label, "text": text, "role": role, "extra": dict(extra or {})}
    probe: dict = {"kind": kind}
    _stamp_piece(probe, piece)
    ev["piece"], ev["piece_src"] = probe.get("piece"), probe.get("piece_src")
    try:
        FORWARD["fn"](ev)
    except Exception as e:  # noqa: BLE001 — the stream never breaks the voice
        logger.debug(f"observer_link.forward: {e!r}")
    return ev
