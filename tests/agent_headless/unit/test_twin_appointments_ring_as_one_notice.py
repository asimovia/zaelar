"""Two appointments with the same words at the same instant ring as ONE notice (E0, node 3.205).

Measured 2026-11-12 at one boot: 723 `cron.create` in 3.6 s for 154 distinct (title, instant) pairs — a calendar that
held the same appointment up to 24 times got one alarm per row, and the alarm said the same words at the same minute
24 times. Now `_schedule_reminder` answers with the pending twin's id instead of creating another, and
`_cancel_reminder` keeps a shared job while any other row still carries it.

Disarms (each seen red): drop the `_twin` lookup → two creates; drop the `_shared` check → the twin's alarm is gone.
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
    me = {"title": "Dentist", "date": DAY, "startTime": "17:00", "reminder_id": "9"}
    reminders._cancel_reminder(me, {"meetings": [dict(me)]})
    assert journal["cancelled"] == ["7", "9"], "a local row read back from the store is itself, by what and when"
    with reminders.rows_in_hand({"meetings": [a, b]}):
        reminders._cancel_reminder(a)
    assert journal["cancelled"] == ["7", "9"], "a bulk sweep hands its rows: the twin still rings"
