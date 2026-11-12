"""Two appointments with the same words at the same instant ring as ONE notice (E0, node 3.205).

Measured 2026-11-12 at one boot: 723 `cron.create` in 3.6 s for 154 distinct (title, instant) pairs — a calendar that
held the same appointment up to 24 times got one alarm per row, and the alarm said the same words at the same minute
24 times. Now `_schedule_reminder` answers with the pending twin's id instead of creating another, and
`_cancel_reminder` keeps a shared job while any other row still carries it.

Disarms (each seen red): drop the `_twin` lookup → two creates; drop the `_shared` check → the twin's alarm is gone;
tell held rows apart by what they say → collapsing two identical LOCAL rows cancels the alarm of the one that stays.
"""
from __future__ import annotations

import pytest

from nucleo.pulse import scheduler
from widgets.agenda import reminders

DAY = "2031-03-10"


@pytest.fixture
def journal(monkeypatch):
    jobs: list[dict] = []

    def create(prompt, schedule, name="", repeat="", now=None, origin="cron"):
        jobs.append({"id": str(len(jobs) + 1), "detail": {"origin": origin, "name": name, "prompt": prompt,
                                                           "schedule": {"display": schedule}}})
        return {"ok": True, "id": jobs[-1]["id"], "display": schedule}
    cancelled: list[str] = []
    monkeypatch.setattr(scheduler, "create", create)
    monkeypatch.setattr(scheduler, "pending_carrying", lambda key: [j for j in jobs if j["detail"].get(key)])
    monkeypatch.setattr(scheduler, "supersede_loose_notices", lambda *a, **k: [])
    monkeypatch.setattr(scheduler, "cancel", lambda ref: cancelled.append(str(ref)) or True)
    return {"jobs": jobs, "cancelled": cancelled}


def test_a_twin_appointment_shares_the_pending_notice_instead_of_creating_another(journal):
    a = reminders._schedule_reminder("Reunión con Marta", DAY, "10:00")
    b = reminders._schedule_reminder("Reunión con Marta", DAY, "10:00")
    assert a == ("1", f"{DAY} 08:00") and b == a, (a, b)
    assert len(journal["jobs"]) == 1, "one alarm for one set of words at one instant"


def test_other_words_or_another_instant_get_their_own_notice(journal):
    reminders._schedule_reminder("Reunión con Marta", DAY, "10:00")
    assert reminders._schedule_reminder("Reunión con Marta", DAY, "12:00")[0] == "2"
    assert reminders._schedule_reminder("Meeting with Mark", DAY, "10:00")[0] == "3"
    assert len(journal["jobs"]) == 3


def test_a_shared_notice_is_kept_while_another_row_carries_it(journal):
    a = {"googleId": "g1", "title": "Reunión con Marta", "reminder_id": "7"}
    b = {"googleId": "g2", "title": "Reunión con Marta", "reminder_id": "7"}
    reminders._cancel_reminder(a, {"meetings": [a, b]})
    assert journal["cancelled"] == [], "the twin still rings"
    reminders._cancel_reminder(a, {"meetings": [a]})
    assert journal["cancelled"] == ["7"], "the last row to carry it takes the alarm with it"
    with reminders.rows_in_hand({"meetings": [a, b]}):
        reminders._cancel_reminder(a)
    assert journal["cancelled"] == ["7"], "a bulk sweep hands its rows: the twin still rings"


def test_a_local_row_read_back_from_the_store_is_itself_by_what_and_when(journal, monkeypatch):
    """Nobody holds rows (a caller outside an action): the store's copy of this meeting is the one EQUAL row."""
    from widgets.agenda import data
    me = {"title": "Dentist", "date": DAY, "startTime": "17:00", "reminder_id": "9"}
    monkeypatch.setattr(data, "load_db", lambda: {"meetings": [dict(me), dict(me)]})
    reminders._cancel_reminder(me)
    assert journal["cancelled"] == [], "its own copy and a twin: the twin still rings"
    monkeypatch.setattr(data, "load_db", lambda: {"meetings": [dict(me)]})
    reminders._cancel_reminder(me)
    assert journal["cancelled"] == ["9"], "only its own copy carries it"


def test_two_identical_local_rows_are_two_rows_and_the_survivor_keeps_its_notice(journal):
    """Local rows carry no id, and twins are EQUAL dicts: told apart by what they say, the twin read as «this same
    row» and removing one cancelled the job the other rings by. In the rows a caller holds a row is itself by
    identity. Disarm: `_shared` back to `not _same_row(m, meeting)` → the first assert goes red."""
    one = {"title": "Dentist", "date": DAY, "startTime": "17:00", "reminder_id": "9"}
    two = dict(one)
    db = {"meetings": [one, two]}
    reminders._cancel_reminder(two, db)
    assert journal["cancelled"] == [], "the survivor still rings"
    db["meetings"] = [m for m in db["meetings"] if m is not two]      # by identity: `remove` would take `one`
    fresh = dict(one)                       # a row just written, not yet among the rows held: the twin is another row
    reminders._cancel_reminder(fresh, db)
    assert journal["cancelled"] == []
    reminders._cancel_reminder(one, db)
    assert journal["cancelled"] == ["9"], "the last row to carry it takes the alarm with it"


def test_collapsing_local_twins_through_the_agenda_door_keeps_the_one_alarm(journal, tmp_path, monkeypatch):
    """The whole path, on a store: two identical local appointments share one notice; «leave one» keeps it ringing,
    and cancelling the one that is left cancels it."""
    from widgets import store
    from widgets.agenda import data, sweep
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(sweep.gcal, "delete_google", lambda m: True)
    row = {"title": "Dentist", "date": DAY, "startTime": "17:00", "reminder_id": "9"}
    db = data.load_db()
    db["meetings"] = [dict(row), dict(row)]
    store.save("agenda", db)
    assert data.apply_action("dedupe_meetings", {"title": "Dentist"}).get("ok") is not False
    assert len(data.load_db()["meetings"]) == 1 and journal["cancelled"] == [], journal["cancelled"]
    assert data.apply_action("cancel_meeting", {"title": "Dentist", "date": DAY}).get("ok") is not False
    assert journal["cancelled"] == ["9"]
