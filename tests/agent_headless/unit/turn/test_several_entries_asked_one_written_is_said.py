"""Several entries asked, one written: the mouth says the rest is not done.

Measured on a text session (2026-11-16): «Also add: Tuesday 9am team standup, Wednesday 3pm coffee, Thursday 6pm piano
lesson, and Sunday 11am brunch» → ONE `agenda:add_meeting` call landed and the reply was «Done.»; the same day a list
asked for with eight things in it was created empty under the same «Done.». `acts_asked` cannot see either: the same
thing done to several entries is one act. How many NEW ENTRIES his words name is its own question at the call door
(`items_asked`); sure of several, with exactly one call that carries no list and landed as the turn's only op, the
mouth says only part was done — and that line takes the place of the canned ack.

The question itself is measured on the real decision model by the opt-in bench
`tests/voice/bench/test_the_items_asked_question_against_the_real_api.py`.
"""
from __future__ import annotations

import asyncio
import importlib
import pathlib

import pytest

from nucleo import canvas_focus
from nucleo.circuit import verdict as V
from nucleo.turn import brief, brief_doors, items_asked, reply, verdicts


class _Done:
    def __init__(self, res):
        self._r = res

    def done(self):
        return True

    def cancelled(self):
        return False

    def result(self):
        return self._r


OK = {"ok": True}
SP = type("S", (), {"sanitize": staticmethod(lambda t, **_: t)})
ONE_MEETING = [{"name": "widget_data", "args": {"widget_id": "agenda", "action": "add_meeting",
                                                "payload": {"title": "Sprint review", "date": "2031-03-04"}}}]


@pytest.fixture
def turn(monkeypatch):
    st = {"choice": items_asked.SEVERAL, "conf": 0.97}
    monkeypatch.setattr(verdicts, "read", lambda h, key, fb, min_confidence=None:
                        (st["choice"], {"confidence": st["conf"]})
                        if key == items_asked.KEY and st["conf"] >= (min_confidence or 0) else (fb, None))
    monkeypatch.setattr(canvas_focus, "this_turn_acts", lambda: [])
    monkeypatch.setattr("nucleo.turn.brief_turn.of_this_turn", lambda: {})
    return st


def _say(tasks, calls, said=""):
    out = []
    text = asyncio.run(reply.after_acts(tasks, said, out.append, SP, model_calls=calls))
    return text, out


def test_the_question_is_asked_at_the_call_door_in_the_same_trip_as_the_acts():
    assert brief_doors.door_of(items_asked.KEY) == "call"
    assert items_asked.KEY in brief.keys() and items_asked.KEY not in brief.build("hola")
    assert brief_doors.keys("call").index(items_asked.KEY) == 1, "one door, one trip: it rides with `acts_asked`"


@pytest.mark.parametrize("lang, word, card, action", [
    ("en", "part", "agenda", "add_meeting"),
    ("es", "parte", "notas", "add_note"),            # another language, another card: the class, not the case
])
def test_several_named_and_one_written_says_the_rest_is_not_done(turn, monkeypatch, lang, word, card, action):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    calls = [{"name": "widget_data", "args": {"widget_id": card, "action": action, "payload": {"title": "x"}}}]
    text, out = _say([(f"{card}::{action}", _Done(OK))], calls)
    assert out and word in out[-1], f"one entry of several was written and nothing said so: {out}"
    assert text.strip(), "the turn is no longer silent: the canned «Done.» has nothing to stand on"


def test_a_call_that_carries_a_list_wrote_them_all(turn):
    calls = [{"name": "widget_data", "args": {"widget_id": "agenda", "action": "add_list",
                                              "payload": {"name": "Hardware store", "items": ["nails", "glue"]}}}]
    _t, out = _say([("agenda::add_list", _Done(OK))], calls)
    assert not out, out


def test_one_call_per_entry_owes_nothing(turn):
    calls = ONE_MEETING * 3
    _t, out = _say([("agenda::add_meeting", _Done(OK))] * 3, calls)
    assert not any("part" in o for o in out), out


@pytest.mark.parametrize("choice, conf", [(items_asked.ONE, 0.99), (items_asked.SEVERAL, 0.6)])
def test_one_entry_named_or_a_doubt_says_nothing(turn, choice, conf):
    turn["choice"], turn["conf"] = choice, conf
    _t, out = _say([("agenda::add_meeting", _Done(OK))], ONE_MEETING)
    assert not out, out


def test_a_turn_that_wrote_nothing_is_another_doors(turn):
    assert items_asked.left_undone([], ONE_MEETING, brief={}) == []


def test_the_line_is_an_unmet_verdict_always_said(turn):
    got = items_asked.left_undone([("agenda::add_meeting", None)], ONE_MEETING, brief={})
    assert len(got) == 1 and got[0].verdict == V.UNMET.name and got[0].said and got[0].card == "agenda"


def test_disarmed_the_reply_stops_reading_the_entries_and_done_stands_alone(turn, monkeypatch):
    """The disarm: take the reader out of the reply's sum and the half-done turn goes back to saying nothing."""
    src = pathlib.Path(reply.__file__)
    original = src.read_text(encoding="utf-8")
    wired = '                + await __import__("nucleo.turn.items_asked", fromlist=["x"]).owed(tasks, model_calls)'
    assert wired in original, "the reply no longer reads `items_asked` where this disarm expects it"
    try:
        src.write_text(original.replace(wired, "                + []"), encoding="utf-8")
        mutated = importlib.reload(reply)
        out: list = []
        asyncio.run(mutated.after_acts([("agenda::add_meeting", _Done(OK))], "", out.append, SP,
                                       model_calls=ONE_MEETING))
        assert not out, "the mutation did not land: the line is still said"
    finally:
        src.write_text(original, encoding="utf-8")
        for pyc in (src.parent / "__pycache__").glob("reply.*.pyc"):
            pyc.unlink()
        importlib.reload(reply)
    _t, out = _say([("agenda::add_meeting", _Done(OK))], ONE_MEETING)
    assert out, "restored: the line is said again"
