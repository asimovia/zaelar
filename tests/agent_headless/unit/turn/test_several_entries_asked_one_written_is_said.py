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
    """The disarm: take the reading out of the call door's sum and the half-done turn goes back to saying nothing."""
    from nucleo.turn import acts_asked
    src = pathlib.Path(acts_asked.__file__)
    original = src.read_text(encoding="utf-8")
    wired = " + items_asked.left_undone(tasks, model_calls, brief=brief)"
    assert wired in original, "the call door no longer reads `items_asked` where this disarm expects it"
    try:
        src.write_text(original.replace(wired, ""), encoding="utf-8")
        importlib.reload(acts_asked)
        _t, out = _say([("agenda::add_meeting", _Done(OK))], ONE_MEETING)
        assert not out, "the mutation did not land: the line is still said"
    finally:
        src.write_text(original, encoding="utf-8")
        for pyc in (src.parent / "__pycache__").glob("acts_asked.*.pyc"):
            pyc.unlink()
        importlib.reload(acts_asked)
    _t, out = _say([("agenda::add_meeting", _Done(OK))], ONE_MEETING)
    assert out, "restored: the line is said again"


# ── audit 2026-11-17: only a write that LANDED is «part», only writes are counted, only the declared rows slot ──────

REFUSED = {"ok": False, "error": "the day is missing"}


def _mutated(module, old, new):
    """Rewrite `old` → `new` in the module's source and reload it; returns the restore."""
    src = pathlib.Path(module.__file__)
    original = src.read_text(encoding="utf-8")
    assert old in original, f"{src.name}: the disarm no longer finds its line"
    src.write_text(original.replace(old, new), encoding="utf-8")
    importlib.reload(module)

    def restore():
        src.write_text(original, encoding="utf-8")
        for pyc in (src.parent / "__pycache__").glob(f"{src.stem}.*.pyc"):
            pyc.unlink()
        importlib.reload(module)
    return restore


@pytest.mark.parametrize("res", [REFUSED, {"ok": False, "verdict": "asked", "say": "widgets.agenda.notice_when"}])
def test_a_single_write_that_was_refused_is_never_done_in_part(turn, monkeypatch, res):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    _t, out = _say([("agenda::add_meeting", _Done(res))], ONE_MEETING)
    assert out and not any("part" in o for o in out), f"nothing was written and «part» was claimed: {out}"


def test_the_acts_reading_does_not_count_a_refused_write_either(turn, monkeypatch):
    from nucleo.turn import acts_asked
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    monkeypatch.setattr(verdicts, "read", lambda h, key, fb, min_confidence=None: (acts_asked.SEVERAL, {"confidence": 0.97}))
    assert acts_asked.ran([("agenda::add_meeting", _Done(REFUSED))]) == []
    _t, out = _say([("agenda::add_meeting", _Done(REFUSED))], ONE_MEETING)
    assert not any("part" in o for o in out), out
    _t, out = _say([("agenda::add_meeting", _Done(REFUSED)), ("notas::add_note", _Done(OK))], ONE_MEETING)
    assert any("part" in o for o in out), "one of two acts landed: that IS part"


def test_a_call_that_writes_nothing_beside_the_write_is_not_counted(turn, monkeypatch):
    """The usual shape: one entry written and the card shown. The show is not a second entry."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    calls = ONE_MEETING + [{"name": "show_widget", "args": {"widget_id": "agenda"}}]
    _t, out = _say([("agenda::add_meeting", _Done(OK))], calls)
    assert any("part" in o for o in out), f"one of several was written beside a show and nothing said so: {out}"


def test_a_list_that_is_a_detail_of_one_entry_is_not_its_rows(turn, monkeypatch):
    """Who comes to ONE appointment is a list and is one entry; only a slot the card declares as rows carries several."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    calls = [{"name": "widget_data", "args": {"widget_id": "agenda", "action": "add_meeting", "payload": {
        "title": "Sprint review", "date": "2031-03-04", "attendees": ["Ilse Brandt", "Teo Varga"], "days": ["mon", "thu"]}}}]
    _t, out = _say([("agenda::add_meeting", _Done(OK))], calls)
    assert out and "part" in out[-1], out
    assert items_asked._rows_slots("agenda", "add_list") == ["items"] and items_asked._rows_slots("agenda", "add_meeting") == []


def test_rows_given_as_one_text_are_several_rows(turn):
    calls = [{"name": "widget_data", "args": {"widget_id": "agenda", "action": "add_list",
                                              "payload": {"name": "Hardware store", "items": "nails, glue; tape"}}}]
    _t, out = _say([("agenda::add_list", _Done(OK))], calls)
    assert not out, out


def test_disarmed_a_refused_write_is_called_part_again(turn, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    restore = _mutated(items_asked, "acts_asked.refused(ops[0][1]) or ", "")
    try:
        _t, out = _say([("agenda::add_meeting", _Done(REFUSED))], ONE_MEETING)
        assert any("part" in o for o in out), "the mutation did not land"
    finally:
        restore()
    _t, out = _say([("agenda::add_meeting", _Done(REFUSED))], ONE_MEETING)
    assert not any("part" in o for o in out)


def test_disarmed_any_call_counts_and_any_list_hides_the_rest_again(turn, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    calls = [{"name": "widget_data", "args": {"widget_id": "agenda", "action": "add_meeting", "payload": {
        "title": "Sprint review", "attendees": ["Ilse Brandt", "Teo Varga"]}}}]
    restore = _mutated(items_asked, "for k in _rows_slots(card, action))", "for k in payload)")
    try:
        _t, out = _say([("agenda::add_meeting", _Done(OK))], calls)
        assert not out, "the mutation did not land"
    finally:
        restore()
    restore = _mutated(items_asked, "    if len(writes) != 1:\n", "    if len([c for c in model_calls or ()]) != 1:\n")
    try:
        _t, out = _say([("agenda::add_meeting", _Done(OK))], ONE_MEETING + [{"name": "show_widget", "args": {}}])
        assert not out, "the mutation did not land"
    finally:
        restore()
    _t, out = _say([("agenda::add_meeting", _Done(OK))], calls)
    assert out and "part" in out[-1]
