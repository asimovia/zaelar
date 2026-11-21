"""A process that has NOT started is told as what it is, and his word can start it (V2-935).

Measured on his engine (2026-11-18, 12:59–13:21): with the host saturated, a worker was held at the gate for twenty
minutes («the voice goes first», `workers/envelope`). The board listed it as running, four of his turns were delivered
to it and each got «got it, I'm on it»; asked why it took so long, the assistant said it would relaunch it and
relaunched nothing; and nothing ever told him it had not begun.

The gate's hold is right — a worker started on a starved host is what starves the voice — but it has to be SAID, and
it is his to overrule:

  · the board lists such a process as `HELD` («NOT STARTED yet»), so the decision reads its true state;
  · words of his that it takes are kept for when it starts, and the line he hears says exactly that — not started,
    kept, and that he can have it started anyway (`line_key`);
  · «start it anyway» is the decision's `go`: the record is marked and the gate lets it in at its next look, held then
    only by the memory floor (`start_now`). A `go` for a process that already runs is just his words to it.
"""
from __future__ import annotations

from loguru import logger

from nucleo.switchboard import board as _board

#: What the decision calls his order to start, now, a process that has not started.
GO = "go"
#: The lines of a held process (`nucleo/wording.FACTS`, and the language's own line as example and last resort).
KEPT, STARTING = "kept_until_start", "starting_anyway"


def mark(rec, why: str) -> None:
    """The gate holds `rec`'s worker for `why`: the record says so, and since when (the board, the turn's facts and the
    pulse read it). The session clears it when it is admitted."""
    import time
    if not getattr(rec, "held", ""):
        rec.held_since = time.time()
    rec.held = why


def forced(rec) -> bool:
    """He said «start it anyway» for this record (`start_now`)."""
    return bool(getattr(rec, "start_now", False))


def is_held(p: dict) -> bool:
    return (p or {}).get("state") == _board.HELD


def start_now(p: dict) -> bool:
    """His «start it anyway» for process `p`: True when it had not started and is now let in at the gate."""
    if not (is_held(p) and p.get("dispatch")):
        return False
    try:
        from nucleo import dispatch
        rec = dispatch.get_record(p["dispatch"])
        if rec is None or not getattr(rec, "held", ""):
            return False
        rec.start_now = True
        from voice.observer import emit
        emit("task", "▶️ started on his word — the gate lets it in", text=str(p.get("title") or "")[:160], role="system",
             extra={"id": str(p["dispatch"]), "task_id": str(p.get("key") or ""), "was": str(rec.held)})
        return True
    except Exception as e:  # noqa: BLE001 — unreached: nothing is claimed, his words go to the process as words
        logger.warning(f"switchboard: could not start {p.get('key')} on his word — {e!r}")
        return False

