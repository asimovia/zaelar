"""One waiting row is never asked «which of these tasks?», and a sure screen order is never taken as its answer
(V2-903 a5, the phone session: five turns).

A row waited for his answer since days before. Every turn its question rode the prompt, the model called
`answer_worker`, the binding had no verdict and asked «¿Para cuál de estas tareas…?» over ONE row — once instead of
running «cierra todos los widgets». Two classes:
  · «which of these tasks» needs two: one row is asked ITS question again (its candidates), never a pick among one;
  · a turn the brief reads as a sure order on the screen (a canvas close/show, a card's act) that does not surely
    pick the row is not its answer: nothing is bound and nothing is asked.
The old row itself is his to close. Disarms: `_which` returning ASK_WHICH for one row; `_screen_order` answering False.
"""
from __future__ import annotations

import threading

import pytest

from nucleo.cli import worker_api_bind as bind
from nucleo.turn import brief as _tb

ROW = {"ask_id": "a-1", "task_id": "t-1", "title": "close the jobs in the browser", "question": "Which one, Ava?",
       "candidates": [{"label": "the sheet"}, {"label": "the browser"}]}
OTHER = {"ask_id": "a-2", "task_id": "t-2", "title": "book a table for four", "question": "Which night?"}


def _brief(answers: dict):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-9", "open_ids": ["musica", "agenda"],
            "result": {k: {"choice": c, "confidence": f} for k, (c, f) in answers.items()}}


def test_one_row_with_candidates_is_asked_its_own_question():
    how, asks = bind.bind(_brief({}), model_answered=True, asks=[ROW])
    assert how == bind.REASK and asks == [ROW], how


def test_two_rows_are_still_asked_which():
    how, asks = bind.bind(_brief({}), model_answered=True, asks=[ROW, OTHER])
    assert how == bind.ASK_WHICH and len(asks) == 2


@pytest.mark.parametrize("order", [
    {_tb.CANVAS_KEY: ("close", 0.95)},                         # «cierra todos los widgets» / «close all the widgets»
    {_tb.TARGET_KEY: ("musica:pause", 0.9)},                   # «para la música» / «pause the music»
])
def test_a_sure_screen_order_is_not_the_rows_answer(order):
    """No pick of a row, and the model did not answer one: the order on screen is the turn — nothing is bound."""
    how, asks = bind.bind(_brief(order), model_answered=False, asks=[ROW, OTHER])
    assert (how, asks) == (bind.NOTHING, []), how


def test_a_doubt_beside_a_screen_order_is_asked_never_dropped():
    """Audit P2-2: «sí, y cierra la música» with an unsure pick — the row is asked, never left waiting in silence; and
    the model's own `answer_worker` beside a screen order is asked too."""
    b = _brief({bind.KEY: ("a-1" + bind.PICK + "0", 0.55), _tb.CANVAS_KEY: ("close", 0.9)})
    assert bind.bind(b, model_answered=False, asks=[ROW, OTHER]) == (bind.REASK, [ROW])
    how, asks = bind.bind(_brief({_tb.CANVAS_KEY: ("close", 0.95)}), model_answered=True, asks=[ROW])
    assert (how, asks) == (bind.REASK, [ROW])


@pytest.mark.parametrize("model", [True, False])
def test_a_none_under_the_veto_with_one_row_is_never_which_of_these(model):
    """Audit P2-1: `none` at 0.7 — a doubt — with ONE row waiting asked «¿para cuál de estas tareas?» over one."""
    how, asks = bind.bind(_brief({bind.KEY: ("none", 0.7)}), model_answered=model, asks=[ROW])
    assert how != bind.ASK_WHICH, how


def test_a_sure_pick_of_the_row_still_binds_with_a_screen_word():
    """«close the browser one» answering «which one?»: the verdict picks the row's candidate — that is his answer."""
    b = _brief({bind.KEY: ("a-1" + bind.PICK + "1", 0.95), _tb.CANVAS_KEY: ("close", 0.9)})
    how, asks = bind.bind(b, model_answered=True, asks=[ROW])
    assert how == bind.ANSWER and asks[0]["ask_id"] == "a-1" and asks[0]["choice"] == 1


def test_a_none_beside_a_sure_screen_order_asks_nothing():
    """Audit P2-1: `none` at 0.7 is no pick of a row — with a sure screen order it is the screen's turn, not «which?»."""
    b = _brief({bind.KEY: ("none", 0.7), _tb.CANVAS_KEY: ("close", 0.95)})
    assert bind.bind(b, model_answered=False, asks=[ROW, OTHER]) == (bind.NOTHING, [])
