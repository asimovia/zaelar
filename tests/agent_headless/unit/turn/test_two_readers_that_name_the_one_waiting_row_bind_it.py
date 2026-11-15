"""The model answering the ONE waiting row, and the reader naming that same row however unsure, bind it (2.1631).

A row waited for his answer, the model routed his restated order to it (`answer_worker`) and the binding reader named
that very row, below the act floor. The binding asked the row's question again instead of binding it — the same
outcome as no verdict at all would have given (ANSWER), made worse by a second reader that agreed. Now, before the
final `_which`: model answered + exactly one row waits + it has no candidates + the reader's choice names that row
(any confidence, never `none`) → ANSWER. A `none`, two rows, a row with candidates, or no answer from the model keep
what they did.

Disarm (seen red, in memory): the module re-read without that branch → the unsure pick of the one row is asked again.
"""
from __future__ import annotations

import inspect
import threading
import types

import pytest

from nucleo.cli import worker_api_bind as bind

ROW = {"ask_id": "a-1", "task_id": "t-1", "title": "create the group", "question": "Shall I create the group?"}
PICKS = {**ROW, "ask_id": "a-3", "candidates": [{"label": "WhatsApp"}, {"label": "Telegram"}]}
OTHER = {"ask_id": "a-2", "task_id": "t-2", "title": "book a table for four", "question": "Which night?"}


def _brief(answers: dict):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-9", "open_ids": [],
            "result": {k: {"choice": c, "confidence": f} for k, (c, f) in answers.items()}}


def test_the_model_and_an_unsure_reader_naming_the_one_row_bind_it(b=bind):
    how, asks = b.bind(_brief({b.KEY: ("a-1", 0.30)}), model_answered=True, asks=[ROW])
    assert (how, asks) == (b.ANSWER, [ROW]), how


def test_a_none_from_the_reader_is_not_the_rows_answer():
    how, asks = bind.bind(_brief({bind.KEY: ("none", 0.82)}), model_answered=True, asks=[ROW])
    assert (how, asks) == (bind.REASK, [ROW]), how


def test_two_waiting_rows_are_unchanged():
    how, asks = bind.bind(_brief({bind.KEY: ("a-1", 0.30)}), model_answered=True, asks=[ROW, OTHER])
    assert how == bind.ASK_WHICH and len(asks) == 2, how


def test_a_row_with_candidates_is_asked_its_question_again():
    how, asks = bind.bind(_brief({bind.KEY: ("a-3", 0.30)}), model_answered=True, asks=[PICKS])
    assert (how, asks) == (bind.REASK, [PICKS]), how


def test_without_the_models_answer_an_unsure_pick_is_asked_again():
    how, asks = bind.bind(_brief({bind.KEY: ("a-1", 0.30)}), model_answered=False, asks=[ROW])
    assert (how, asks) == (bind.REASK, [ROW]), how


def test_disarmed_without_the_branch_the_unsure_pick_is_asked_again():
    """Disarm: the module's source re-read without the agreeing-readers branch → the first test goes red."""
    src = inspect.getsource(bind)
    cut = "        if model_answered and len(asks) == 1 and ask_id in by_id and not asks[0].get(\"candidates\"):\n" \
          "            return ANSWER, asks"
    assert cut in src, "the branch moved: the disarm no longer cuts it"
    mod = types.ModuleType("worker_api_bind_disarmed")
    exec(compile(src.replace(cut, "        pass"), bind.__file__, "exec"), mod.__dict__)
    with pytest.raises(AssertionError):
        test_the_model_and_an_unsure_reader_naming_the_one_row_bind_it(mod)
