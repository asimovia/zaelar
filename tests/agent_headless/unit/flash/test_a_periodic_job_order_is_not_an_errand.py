"""V2-883 — an order over a periodic job is a TURN act through its door, never a Brain Worker errand.

Measured shape: «delete the periodic job of the parcel tracking» became an errand that spent minutes probing cards
for the job's id and never reached the scheduler. The escalate question tells the brief what the assistant does ON
THE SPOT; the cards are listed there, and the scheduler — a door outside the cards — was not, so a sure
`handle_inline` could not be read for it. The door now declares its own turn acts once (`scheduler.TURN_ACTS`) and
both questions that decide whether a worker opens read that declaration: the escalate question and the
capability-gap question (where an undeclared act reads as «missing» or «work»).
"""
from __future__ import annotations

from nucleo.flash import capability_gap, escalation_guard
from nucleo.pulse import scheduler
from nucleo.turn import brief


def test_the_escalate_question_carries_the_schedulers_declared_turn_acts():
    q = brief.escalate_question()
    assert scheduler.TURN_ACTS in q["instructions"], q["instructions"][:400]
    assert scheduler.TURN_ACTS in escalation_guard.declared_turn_acts()


def test_the_declaration_is_the_doors_own_not_a_copy(monkeypatch):
    """Change what the door declares and the question changes with it: one sentence, one owner."""
    monkeypatch.setattr(scheduler, "TURN_ACTS", "his alarms are set and cleared in the turn.")
    assert "his alarms are set and cleared in the turn." in brief.escalate_question()["instructions"]


def test_the_capability_gap_question_lists_it_beside_the_cards():
    q = capability_gap.question([])
    assert q is not None and scheduler.TURN_ACTS in q["instructions"], (q or {}).get("instructions", "")[-400:]
