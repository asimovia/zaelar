"""An agenda write's end state is what THIS call left true — never a row that was already there (2026-11-08).

The circuit renders an action's `done_when` from the call's payload BEFORE the op runs, takes its baselines, and
reads it against the product after. `add_meeting {title: Dentist}` (no date) rendered to «a row titled Dentist
exists», which last month's Dentist already satisfied: the write could fail and read «met». The same hole was in
`move_meeting` without `newDate` (a row with that title at that hour on ANY day), and `cancel_meeting`,
`update_meeting`, `set_reminder` and `add_task` declared no end state at all.

The class: a row of `meetings` cannot tell a new write from an old one (meetings have no id). The card now records
each meeting write that lands (`widgets/agenda/writes.py`, the `writes` collection) and every end state pairs the
real outcome with `writes … expect: added` — an entry that did not exist when the request was born. Each test reads
the rendered end state BEFORE the op (must not be met) and AFTER it (must be met).
"""
from __future__ import annotations

import datetime as _dt

import pytest

AHEAD = (_dt.date.today() + _dt.timedelta(days=20)).isoformat()
PAST = (_dt.date.today() - _dt.timedelta(days=20)).isoformat()


@pytest.fixture
def ag(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.agenda import data as _d
    from widgets.agenda import gcal
    monkeypatch.setattr(gcal, "svc", lambda: None)          # no calendar connected: nothing leaves this machine
    return _d


def _born(action, payload):
    from nucleo.circuit import spec
    dw = spec.render("agenda", action, payload)
    assert dw, f"agenda:{action} declares no renderable end state for {payload}"
    return dw


def _met(dw):
    from nucleo.circuit import verify
    return verify.check(dw)


def test_an_add_without_a_date_is_not_met_by_last_months_row(ag):
    ag.apply_action("add_meeting", {"title": "Dentist", "date": PAST, "startTime": "10:00"})
    dw = _born("add_meeting", {"title": "Dentist", "startTime": "11:00"})
    assert _met(dw) is False, "the older Dentist met the end state of a write that has not run"
    ag.apply_action("add_meeting", {"title": "Dentist", "startTime": "11:00"})
    assert _met(dw) is True


def test_an_add_whose_write_was_refused_stays_unmet(ag):
    ag.apply_action("add_meeting", {"title": "Piano lesson", "date": PAST, "startTime": "10:00"})
    dw = _born("add_meeting", {"title": "Piano lesson"})
    ag.apply_action("add_meeting", {"title": "Piano lesson", "date": "not a date at all", "repeat": "nonsense"})
    ag.apply_action("add_meeting", {"title": ""})          # refused: no title
    assert _met(dw) is not True


def test_a_move_without_a_new_day_needs_THIS_move(ag):
    ag.apply_action("add_meeting", {"title": "Yoga", "date": AHEAD, "startTime": "18:00"})
    dw = _born("move_meeting", {"title": "Yoga", "newTime": "18:00"})
    assert _met(dw) is False, "a Yoga already at 18:00 met the end state of a move that has not run"
    ag.apply_action("move_meeting", {"title": "Yoga", "newTime": "18:00"})
    assert _met(dw) is True


def test_a_cancel_is_met_when_the_occurrence_is_gone_and_only_then(ag):
    ag.apply_action("add_meeting", {"title": "Haircut", "date": AHEAD, "startTime": "12:00"})
    dw = _born("cancel_meeting", {"title": "Haircut"})
    assert _met(dw) is False
    ag.apply_action("cancel_meeting", {"title": "Haircut"})
    assert _met(dw) is True


def test_a_cancel_of_one_day_of_a_series_reads_that_day(ag):
    ag.apply_action("add_meeting", {"title": "Flute", "date": AHEAD, "startTime": "17:00", "repeat": "weekly"})
    from widgets import store
    first = store.load("agenda", {})["meetings"][0]["date"]
    dw = _born("cancel_meeting", {"title": "Flute", "date": first})
    assert _met(dw) is False
    ag.apply_action("cancel_meeting", {"title": "Flute", "date": first})
    assert _met(dw) is True, "one day of the series went and the rest stays: that is the end state"


def test_an_edit_is_met_by_THIS_edit(ag):
    ag.apply_action("add_meeting", {"title": "Lunch with Ana", "date": AHEAD, "startTime": "14:00"})
    dw = _born("update_meeting", {"title": "Lunch with Ana", "newTitle": "Lunch with Ana and Luis"})
    assert _met(dw) is False
    ag.apply_action("update_meeting", {"title": "Lunch with Ana", "newTitle": "Lunch with Ana and Luis"})
    assert _met(dw) is True


def test_a_notice_is_not_met_by_the_default_notice_every_row_carries(ag):
    ag.apply_action("add_meeting", {"title": "Accountant", "date": AHEAD, "startTime": "16:00"})
    from widgets import store
    assert store.load("agenda", {})["meetings"][0].get("remindAt"), "precondition: the default notice is set"
    dw = _born("set_reminder", {"title": "Accountant", "at": "15:00"})
    assert _met(dw) is False, "the default notice met the end state of a set_reminder that has not run"
    ag.apply_action("set_reminder", {"title": "Accountant", "at": "15:00"})
    assert _met(dw) is True


def test_a_task_is_met_by_a_NEW_task_not_by_the_one_already_done(ag):
    ag.apply_action("add_task", {"title": "Buy bread"})
    dw = _born("add_task", {"title": "Buy bread"})
    assert _met(dw) is False, "yesterday's «Buy bread» met the end state of an add that has not run"
    ag.apply_action("add_task", {"title": "Buy bread"})
    assert _met(dw) is True


def test_a_task_the_card_turns_into_an_appointment_is_still_met(ag):
    """A dated task that asks for a notice is written as an agenda item (V2-781 T515): the end state is met there."""
    payload = {"title": "Renew passport", "date": AHEAD, "remind": f"{AHEAD} 09:00"}
    dw = _born("add_task", payload)
    assert _met(dw) is False
    ag.apply_action("add_task", payload)
    assert _met(dw) is True


def test_the_title_as_the_call_said_it_meets_the_end_state(ag):
    """The card rewrites a title before it stores it («Piano del martes 2026-10-13» names that day, V2-781); the end
    state is rendered from the call's words, so the record keeps those words too (`asked`)."""
    ag.apply_action("add_meeting", {"title": "Piano", "date": AHEAD, "startTime": "17:00"})
    said = f"Piano {AHEAD}"
    dw = _born("move_meeting", {"title": said, "newTime": "18:30"})
    ag.apply_action("move_meeting", {"title": said, "newTime": "18:30"})
    from widgets import store
    log = store.load("agenda", {}).get("writes") or []
    assert log and log[-1]["asked"] == said and log[-1]["title"] == "Piano", log
    writes_clause = [c for c in dw["all"] if c.get("collection") == "writes"]
    from nucleo.circuit import verify
    assert verify.check({"all": writes_clause}) is True


def test_the_record_is_bounded(ag):
    from widgets.agenda import writes
    db = {}
    for i in range(writes.KEEP + 15):
        writes.note(db, "add_meeting", {"title": f"t{i}"})
    assert len(db["writes"]) == writes.KEEP and db["writes"][-1]["title"] == f"t{writes.KEEP + 14}"
    assert len({e["id"] for e in db["writes"]}) == writes.KEEP
