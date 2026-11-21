"""Two appointments of one title on the same day are two rows, named by the hour they are at NOW (2026-11-12).

The multi-turn bench, «no, la otra»: a 10:00 and a 17:00 «Meeting with Mark» tomorrow. «Move the 10 am one to noon»
went out as `move_meeting {title, date, newTime}` — nothing told the rows apart, so the move took whichever the list
held first; «no, the other one» re-sent the same call, the move took the row it had just moved, left it where it was,
and the reply said «Done.». Three mechanisms, one per consequence:

  · `currentTime` (the row's hour NOW) narrows the reference — through every verb that finds a row (`sweep._matches`)
    and carried from an `item` reference that names its hour (`ref_day`), the way its day already is;
  · a reference that still finds two rows of one title on one day at different hours, with no `currentTime` and no
    conversation on one of them, ASKS (options with the hours) — never the first in the list;
  · a move that leaves the row where it already is refuses `no_change`: an act that changed nothing is not done.
And the appointment the conversation is on carries its hour, so «it» names one row, not every row of its title.

Disarm each: drop the narrowing, `which`, `unchanged`, or the hour of the focus → red.
"""
from __future__ import annotations

import datetime as dt

import pytest

from widgets import ref_day
from widgets.agenda import data as agenda, gcal, reminders

DAY = (dt.date.today() + dt.timedelta(days=1)).isoformat()


@pytest.fixture(autouse=True)
def _agenda(monkeypatch):
    monkeypatch.setattr(gcal, "svc", lambda: None)
    sched = lambda *a, **k: ("job", "")  # noqa: E731
    for mod in (agenda, reminders):
        monkeypatch.setattr(mod, "_schedule_reminder", sched)
        monkeypatch.setattr(mod, "_cancel_reminder", lambda m: None)
    from widgets import store
    db = agenda.load_db()
    db["meetings"] = [m for m in db.get("meetings") or [] if "Mark" not in str(m.get("title") or "")]
    store.save(agenda.WIDGET_ID, db)
    for start, end in (("10:00", "11:00"), ("17:00", "18:00")):
        assert agenda.apply_action("add_meeting", {"title": "Meeting with Mark", "date": DAY,
                                                   "startTime": start, "endTime": end}).get("ok") is not False
    db = agenda.load_db()
    db.pop("focus", None)                 # the calendar as it stands, no conversation on either row yet
    store.save(agenda.WIDGET_ID, db)


def _starts() -> list[str]:
    return sorted(str(m.get("startTime")) for m in agenda.load_db()["meetings"] if "Mark" in m.get("title", ""))


def test_the_hour_it_is_at_now_names_the_row():
    res = agenda.apply_action("move_meeting", {"title": "Meeting with Mark", "date": DAY, "currentTime": "17:00",
                                               "newTime": "12:00"})
    assert res.get("ok") is not False, res
    assert _starts() == ["10:00", "12:00"]


def test_without_the_hour_two_rows_of_one_title_on_one_day_are_asked():
    res = agenda.apply_action("move_meeting", {"title": "Meeting with Mark", "date": DAY, "newTime": "12:00"})
    assert res.get("ok") is False and res.get("error") == "ambiguous", res
    assert any("10:00" in o for o in res["options"]) and any("17:00" in o for o in res["options"])
    assert _starts() == ["10:00", "17:00"], "an ambiguous reference moved a row"


def test_a_move_that_changes_nothing_is_not_done():
    assert agenda.apply_action("move_meeting", {"title": "Meeting with Mark", "date": DAY, "currentTime": "10:00",
                                                "newTime": "12:00"}).get("ok") is not False
    # «no, the other one» re-sent as the same move, on the row the conversation is now on
    res = agenda.apply_action("move_meeting", {"title": "Meeting with Mark", "date": DAY, "newTime": "12:00"})
    assert res.get("ok") is False and res.get("error") == "no_change", res
    assert _starts() == ["12:00", "17:00"]


def test_the_row_the_conversation_is_on_is_named_with_its_hour():
    agenda.apply_action("move_meeting", {"title": "Meeting with Mark", "date": DAY, "currentTime": "17:00",
                                         "newTime": "15:00"})
    # «and make it end at four» — no title: the row just moved, not every row of its title
    res = agenda.apply_action("move_meeting", {"endTime": "16:30"})
    assert res.get("ok") is not False, res
    rows = {m["startTime"]: m["endTime"] for m in agenda.load_db()["meetings"] if "Mark" in m.get("title", "")}
    assert rows == {"10:00": "11:00", "15:00": "16:30"}, rows


def test_a_reference_that_names_its_hour_keeps_it():
    got = ref_day.carried("agenda", "move_meeting", "Meeting with Mark 2026-11-13 17:00", {"title": "Meeting with Mark"})
    assert got.get("currentTime") == "17:00" and got.get("date") == "2026-11-13"
    assert "currentTime" not in ref_day.carried("agenda", "add_meeting", "Lunch 13:00", {"title": "Lunch"})


def test_a_moved_row_says_where_it_was_so_the_move_back_is_one_move():
    """«…and leave the 10 am one as it was»: after the move the 10:00 row is at 12:00, and without its old hour on its
    line the model answered «there is no 10 am one». The digest names it while the conversation lasts."""
    agenda.apply_action("move_meeting", {"title": "Meeting with Mark", "date": DAY, "currentTime": "10:00",
                                         "newTime": "12:00"})
    line = next(ln for ln in agenda.prompt_digest().splitlines() if "12:00" in ln and "Mark" in ln)
    assert "10:00" in line, line
    back = agenda.apply_action("move_meeting", {"title": "Meeting with Mark", "date": DAY, "currentTime": "12:00",
                                                "newTime": "10:00"})
    assert back.get("ok") is not False and _starts() == ["10:00", "17:00"], back

