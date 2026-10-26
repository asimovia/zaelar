"""Is THIS turn an order to stop the errand running now? One enumerated question in the turn's brief (V2-807 T-14).

Two places decide a stop. The tool gate (`tool_executor_calls._t_stop_worker`, GUARD 2) refuses a `stop_worker` the
model chose when the operator did not order it in this turn — its real purpose is context bleed: a complaint two
turns back, dragged forward by the model, must not kill a live errand (2026-08-14). And the settle backstop
(`post_stream_settle`) stops the errand when he ordered it and the model called nothing.

Both read a WORD TABLE to know whether he ordered it, and a word table reads one phrasing. A clear stop in a word
order the table did not list («para inmediatamente esa tarea que está en marcha») was refused twice while the errand
ran on, and widening the table again (V2-585 already did once) would only add the next phrasing. The question is a
judgement about the turn, so it is asked as one: here, inside the brief the turn already pays for (N questions cost
one round trip), and only while an errand is live — with none, the answer is known.

The verdict DECIDES when it is sure (CRIT-K1): a sure «stop» licenses the model's call and repairs a turn that made
none; a sure «keep» refuses a call that is drag. With no sure verdict (brief off, in flight, unsure, or asked before
an errand existed) the grammar keeps today's path, bit for bit — it is handed IN by the caller, never re-read here.
"""
from __future__ import annotations

from loguru import logger

KEY = "stop_errand"

INSTRUCTIONS = (
    "A background task (an errand the assistant is working on for the operator) is running right now. Is the "
    "operator, in THIS message, ordering that running task to stop, be cancelled or be abandoned? Answer 'stop' "
    "only for an order given now — in any wording, word order or language, including a «yes» to our own offer to "
    "stop it. Answer 'keep' for anything else: a complaint or comment about something earlier, a question about the "
    "task, a new request, or an order about a card on screen, a video, music or the assistant's voice.")

CHOICES = {
    "stop": "he orders the task running now to stop or be cancelled, in this message",
    "keep": "anything else: no order to stop that running task in this message",
}


def question(last_reply: str = "") -> dict:
    """The question. Our previous line rides with it: «yes» is a stop only after we offered to stop."""
    lr = (last_reply or "").strip()
    return {"instructions": INSTRUCTIONS + (f" [Our previous reply: {lr[:200]}]" if lr else ""),
            "criteria": dict(CHOICES)}


def verdict(brief) -> str | None:
    """'stop' or 'keep' when the brief is READY and SURE about it; None otherwise. Never waits, never raises."""
    if not brief:
        return None
    try:
        from nucleo.flash import turn_brief as _tb
        choice, info = _tb.read(brief, KEY, None)
    except Exception as e:  # noqa: BLE001 — a classifier may never break a turn
        logger.debug(f"stop_decision: verdict unreadable: {e!r}")
        return None
    return choice if info is not None and choice in CHOICES else None


def ordered(brief, *, grammar: bool) -> bool:
    """Did he order the running errand to stop in this turn? The sure verdict decides; without one, the grammar
    the caller handed in. Read by the tool gate (may the model's `stop_worker` run?) and by the backstop that
    repairs a turn whose model called nothing."""
    v = verdict(brief)
    return grammar if v is None else v == "stop"


def repair(brief, text: str, *, escalating: bool, grammar) -> list:
    """Stop the running errand for a turn that ordered it and whose model did not call `stop_worker`.

    A SURE stop verdict repairs the turn whatever the model did instead — an escalation it started still starts
    («para eso y búscame otra cosa» is both). With no sure verdict, today's path: only a turn that started no
    escalation, read by the grammar (`grammar`, a callable so a sure verdict never pays for it). Returns the ids
    of the tasks it cancelled ([] when it stopped nothing). The caller only calls this when the model did not stop.
    """
    v = verdict(brief)
    if v is None and escalating:
        return []
    from nucleo import dispatch as _dispatch
    if not _dispatch.has_active():
        return []
    if not (v == "stop" if v is not None else bool(grammar())):
        return []
    return list(_dispatch.cancel_soon(text) or [])
