"""A sure verdict's lens that ANSWERS beats the model's lens that answers nothing, on the same app (2.1741).

Demo C2: «find me a free 45 minutes tomorrow afternoon…» — the model called `agenda:show_day` (a view that answers
nothing), the verdict read `agenda:find_free` (a view that answers) at 0.88, and the one gate that lets a verdict's
lens win over the model's lens read `wants_words`, which the brief reads unsure (0.04) on that sentence. Neither
`card.vetoes` clause applied (no write, no state change), the model's view ran, and the reply was «Done.» with no
time. The rule is about what each action DECLARES (`output.answer`), never about his words: a sure verdict naming the
lens that answers takes the place of a lens that answers nothing; below the veto floor nothing changes. Disarm: the
clause removed → red.
"""
from __future__ import annotations

import pytest

from nucleo.acts import card
from nucleo.flash import direct_action as _da


@pytest.fixture
def sure(monkeypatch):
    state = {"sure": True}
    monkeypatch.setattr(_da, "_action_sure", lambda brief, floor=None: state["sure"])
    return state


def test_a_sure_answering_lens_vetoes_a_lens_that_answers_nothing(sure):
    got = card.vetoes(object(), "agenda", "show_day", "find_free")
    assert got and "answers" in got, "the model's mute lens ran over the sure verdict's answer"


def test_below_the_veto_floor_the_models_lens_runs(sure):
    sure["sure"] = False
    assert card.vetoes(object(), "agenda", "show_day", "find_free") == ""


def test_the_models_answering_lens_is_never_vetoed_by_a_mute_one(sure):
    assert card.vetoes(object(), "agenda", "find_free", "show_day") == "", \
        "a lens that answers was replaced by one that answers nothing"
