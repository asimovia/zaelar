"""What the operator is answering: the last line WE said before his turn began (demo, 2026-10-22).

`brain._last_reply` is rewritten on every streamed chunk of the CURRENT reply, so a guard that runs during or
after the stream and reads it as «what we said before» reads our own answer instead. Measured live: «Want me to
start the trip plan again properly?» → «Yes» → the model escalated, and the fragment guard read the reply it was
streaming («I'm on it — a fresh five-day plan…», no question in it) and annulled the commission as a fragment.
Proactive questions never reach `_last_reply` at all: «…running for 15 minutes now. Want me to stop it or keep
going?» → «Yes, please» → the stop was refused as context-bleed.

The fix is one snapshot, taken when the turn's window is built — after the proactive lines we said on our own
are drained into it (`dialog.drain_spoken`) and before the model streams a word. Every reader that asks «did we
just ask him something?» reads THIS, never the live `_last_reply`.
"""
from __future__ import annotations


def snapshot(brain, window) -> str:
    """Freeze the last assistant line of the window as the line this turn answers. Returns it."""
    line = ""
    for m in reversed(list(window or [])):
        if isinstance(m, dict) and m.get("role") == "assistant":
            line = str(m.get("content") or "").strip()
            if line:
                break
    try:
        brain._prior_line = line
    except Exception:  # noqa: BLE001 — a brain without attributes still runs its turn
        pass
    return line


def of(brain) -> str:
    """The line this turn answers. Falls back to `_last_reply` only for a brain that never snapshotted (a test
    double, an old entry point) — the behaviour every reader had before."""
    v = getattr(brain, "_prior_line", None)
    if v is None:
        v = getattr(brain, "_last_reply", "") or ""
    return str(v or "")


def answers_our_question(brief, prior: str) -> bool:
    """The turn is his ANSWER to a question we put to him: the brief's `request_type=answer` AND our prior line
    asked something. Both halves, as `escalation_guard.is_a_fragment` documents: a yes is an answer only where
    there was a question, and a question mark alone is not his answer."""
    try:
        from nucleo.flash import canvas_license as _lic, turn_brief as _tb
        kind, _info = _tb.read(brief, _tb.REQUEST_KEY, "")
        return str(kind or "") == "answer" and _lic.answered_an_offer(prior)
    except Exception:  # noqa: BLE001 — a classifier may never break a turn
        return False
