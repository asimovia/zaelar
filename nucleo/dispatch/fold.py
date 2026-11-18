"""What the dispatcher does with an escalation it folds into an errand that is already open.

Whose his words are is decided once, at the turn's gate (`nucleo/switchboard`). A commission that still reaches the
dispatcher and is the same errand as a live or a parked one — its own dedup: content words, then its model judge —
joins that errand. These are the consequences of that fold: the duplicate's sheet never stays on screen with nobody
behind it, and a parked errand's question stands.
"""
from __future__ import annotations

from loguru import logger


def late_fold(target: str, ctx: dict) -> str:
    """The escalation was folded into live errand `target`: its own sheet, when it is not the target's, is closed
    instead of left on screen with nobody writing into it (2026-10-21, a «Searching in depth…» card with no worker).
    Returns the sheet it closed, "" when none. Never raises."""
    own = str((ctx or {}).get("sheet") or "").strip()
    try:
        from nucleo import dispatch as _d
        rec = _d.get_record(target)
        theirs = str(_d.sheet_of(rec) or "") if rec is not None else ""
    except Exception as e:  # noqa: BLE001
        logger.warning(f"fold: into {target} — target unreadable: {e}")
        theirs = ""
    orphan = own if own and own != theirs else ""
    try:
        if orphan:
            from nucleo.acts import canvas, surface_owner
            from widgets.results import data as _sheet
            surface_owner.orphan(orphan, "closed")
            canvas.apply("close", _sheet.instance_id(orphan), src="system:fold")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"fold: could not close the duplicate's sheet of {target}: {e}")
    return orphan


def ask_again(question: str) -> None:
    """His words joined an errand parked on his yes: its question stands (state the turn already reads). Recorded on
    the timeline, where the battery and the operator's panel see it."""
    try:
        from voice.observer import emit
        emit("flow", "🧵 his words join the errand parked on his yes — its question stands", role="system",
             text=str(question or "")[:160], extra={"cat": "flash", "v": "V2-851"})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"fold: not recorded — {e!r}")
