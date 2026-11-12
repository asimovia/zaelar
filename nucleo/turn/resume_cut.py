"""A reply composed for a sentence he went on with is not part of the conversation (V2-888).

Measured 2026-11-11 (cloud session, Flux ear): «A ver…» [1.7 s] «ponme un videoclip de X». The end of turn committed
«Aversiones.», he resumed 0.1 s later, the turn answered «No te he entendido eso» two seconds after. LiveKit cut that
speech when his voice came back, so he never heard it — but it entered the dialogue window, and the next turn read
«Aversiones.» / «No te he entendido eso» / «ponme un videoclip…»: a misunderstanding that never happened.

The signal is the stream's own `_superseded` (a longer prefix, or his voice resumed after the reply began —
`nucleo.input.typed.resumed_since`). At the close, a superseded turn that did NOTHING leaves his words in the window
(they happened) but not its reply, and the words are owed to the next turn (`stt.unanswered_by`). A turn that acted
keeps its reply: what it did is real and the window must say so.
"""
from __future__ import annotations

from loguru import logger


def reply_unheard(superseded, acted: bool, *, brain, text: str, spoken_text: str, emit) -> bool:
    """True when the reply must stay out of the window. `superseded` is the stream's check (None on a channel with
    none). Owes the words to the next turn and leaves the trace. Never raises."""
    if acted or superseded is None or not str(spoken_text or "").strip():
        return False
    try:
        if not superseded():
            return False
    except Exception as e:  # noqa: BLE001 — no signal is the old behaviour: the reply stays
        logger.debug(f"resume_cut: superseded check failed, the reply stays: {e!r}")
        return False
    from nucleo.input import stt as _acc
    _acc.unanswered_by(brain, text)
    try:
        emit("brain", "🧩 fragmento descartado — la frase seguía", text=str(text or "")[:200], role="system",
             extra={"cat": "flash", "phase": "close", "spent_model": True, "dropped_reply": str(spoken_text)[:200]})
    except Exception as e:  # noqa: BLE001 — the trace is best-effort; the window is not
        logger.debug(f"resume_cut: the trace was not emitted: {e!r}")
    return True
