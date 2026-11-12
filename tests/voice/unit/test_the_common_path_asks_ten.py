"""Node 3.196 — the turn's one Jev trip asks only what the turn itself reads (V2-887 step 8, step 1).

Measured 2026-11-12: `brief.build()` asked 16 questions (21.6k chars) with nothing open, 21 with two cards and a
worker. Six of them were read by ONE door each, on a minority of turns: the acts his words asked (read after a door
ran an act), the errand's consent class, its kind and the capability gap (read at the errand portal), the channel he
named (read where a message leaves) and a rename (read after `set_style_directive`). They are asked at those doors now
(`nucleo/turn/brief_doors`), into the same handle, and the common path asks ten.

The KEY SETS are pinned on four contexts, not the count: a question that silently joins the per-turn trip is how the
brief grew to 22, and one that silently leaves it is how `catalog_widget` was answered into a void for a month.
"""
from __future__ import annotations

import pytest

from nucleo.turn import brief, brief_doors

#: Tier 1 (always) and the per-turn questions read before or by the model on every turn.
COMMON = {"canvas", "request_type", "build_or_use", "escalate_or_inline", "wants_words", "errand_surface",
          "search_module", "login_only", "catalog_widget", "readable"}
#: What open cards add (the screen questions) and take away (the catalogue of nothing open).
WITH_CARDS = (COMMON - {"catalog_widget"}) | {"screen_action", "catalog_closed", "names_a_card", "end_state"}


@pytest.fixture(autouse=True)
def _no_rows(monkeypatch):
    from widgets import refs as _refs   # item_ref is asked only over two listed rows: pinned off here
    monkeypatch.setattr(_refs, "_ref_index", lambda base: [])


def _asked(**kw) -> set:
    return set(brief.build("mándale un whatsapp a Raquel diciendo que llego tarde", **kw))


def test_nothing_open_asks_the_ten():
    assert _asked() == COMMON


def test_two_cards_open_ask_the_screen_questions_and_no_door_question():
    assert _asked(open_ids=["agenda", "mensajeria"]) == WITH_CARDS


def test_a_running_errand_adds_only_its_own_two():
    got = _asked(has_workers=True, running_goals=["find a flat"])
    assert got == COMMON | {"stop_errand", "errand_target"}, got


def test_a_waiting_task_adds_only_the_answer_binding():
    asks = [{"task_id": "b-1", "ask_id": "a1", "question": "¿enduro o cross?", "title": "moto", "since": 0}]
    got = _asked(open_asks=asks)
    assert got == COMMON | {"answers_open_question"}, got


def test_no_door_question_rides_the_turn_trip_in_any_context():
    """The six questions a single door reads are asked at that door (`brief_doors.DOORS`), never per turn."""
    doors = set(brief_doors.keys())
    assert doors == {"acts_asked", "errand_class", "errand_kind", "capability_gap", "message_channel",
                     "identity_change"}
    for kw in ({}, {"open_ids": ["agenda", "mensajeria"]}, {"has_workers": True, "running_goals": ["x"]}):
        assert not _asked(**kw) & doors
    assert set(brief.keys()) >= doors, "the brief may still CARRY them: its doors merge them into the same handle"
