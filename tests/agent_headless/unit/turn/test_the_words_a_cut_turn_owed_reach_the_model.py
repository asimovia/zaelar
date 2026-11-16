"""The words a cut turn still owes ride THIS turn's message to the model.

Measured on a text session (2026-11-16): three typed lines reached the engine within a second. Each cut the one before
it before its first word; the brief judged the three as one sentence (`stt.whole_turn`), and the model — handed them
as three consecutive user messages — served only the last. Two appointments were never written and never mentioned.
The model is now handed what the verdict judged: one user message, the owed sentences first.
"""
from __future__ import annotations

import importlib
import pathlib
import types

import pytest

from nucleo.input import stt
from nucleo.turn import owed_words

A, B, C = "Add a cello lesson on Thursday at 6pm.", "Añade comida con la familia el domingo a las 14.", \
    "Remind me tomorrow at 8am to water the ferns."


@pytest.fixture(autouse=True)
def _no_timeline(monkeypatch):
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: None)


def _window(*owed):
    return ([{"role": "user", "content": "Show my week."}, {"role": "assistant", "content": "Here you go."}]
            + [{"role": "user", "content": o} for o in owed])


def test_two_cut_lines_and_the_third_are_one_message():
    win, mine = owed_words.as_one_message(_window(A, B), C, (C, f"{A} {B} {C}"))
    assert mine.endswith(C) and A in mine and B in mine and mine.index(A) < mine.index(B) < mine.index(C)
    assert [m["content"] for m in win] == ["Show my week.", "Here you go."], "the owed lines are not said twice"


def test_the_turn_text_keeps_what_the_engine_appended_to_it():
    text = f"{C}\n[note: the calendar is open]"
    _win, mine = owed_words.as_one_message(_window(A), text, (C, f"{A} {C}"))
    assert mine == f"{A}\n{text}"


@pytest.mark.parametrize("judged", [None, ("", ""), (C, C), (C, "something else entirely"), ("another line", f"{A} another line")])
def test_a_turn_that_owes_nothing_is_untouched(judged):
    win = _window(A)
    assert owed_words.as_one_message(win, C, judged) == (win, C)


def test_an_answered_line_stays_in_the_window():
    """Only the TRAILING unanswered user lines are the owed ones: what was answered is conversation."""
    win = [{"role": "user", "content": A}, {"role": "assistant", "content": "Added."}, {"role": "user", "content": B}]
    kept, mine = owed_words.as_one_message(win, C, (C, f"{B} {C}"))
    assert [m["content"] for m in kept] == [A, "Added."] and mine.startswith(B)


def test_the_chain_of_cuts_is_what_the_brain_remembers():
    """End to end with the accumulator's own bookkeeping: A cut, then B cut, then C — C's turn carries both."""
    brain = types.SimpleNamespace(_acc=None, _judged_turn=None, _cut_unanswered=None)
    assert stt.whole_turn(brain, A) == A
    stt.unanswered_by(brain, A)
    assert stt.whole_turn(brain, B) == f"{A} {B}"
    stt.unanswered_by(brain, B)
    assert stt.whole_turn(brain, C) == f"{A} {B} {C}"
    _win, mine = owed_words.as_one_message(_window(A, B), C, brain._judged_turn)
    assert A in mine and B in mine and mine.endswith(C)


def test_the_prompt_builder_hands_the_model_the_merged_message():
    src = (pathlib.Path(owed_words.__file__).resolve().parents[2]
           / "voice/engine/llm/providers/turn_prompt.py").read_text(encoding="utf-8")
    assert "_owed.as_one_message(" in src and '{"role": "user", "content": _mine}' in src


def test_disarmed_the_model_gets_only_the_last_line_again():
    src = pathlib.Path(owed_words.__file__)
    original = src.read_text(encoding="utf-8")
    merge = '        return kept, f"{owed}\\n{str(text).strip()}"\n'
    assert merge in original, "the merge is not where this disarm expects it"
    try:
        src.write_text(original.replace(merge, "        return window, text\n"), encoding="utf-8")
        mutated = importlib.reload(owed_words)
        _w, mine = mutated.as_one_message(_window(A, B), C, (C, f"{A} {B} {C}"))
        assert mine == C, "the mutation did not land"
    finally:
        src.write_text(original, encoding="utf-8")
        for pyc in (src.parent / "__pycache__").glob("owed_words.*.pyc"):
            pyc.unlink()
        importlib.reload(owed_words)
    assert A in owed_words.as_one_message(_window(A, B), C, (C, f"{A} {B} {C}"))[1]
