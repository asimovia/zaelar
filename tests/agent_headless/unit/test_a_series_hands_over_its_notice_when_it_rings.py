"""A repeating appointment hands its notice over to the next occurrence the moment it rings (V2-872 F2, node 2.843).

A series keeps ONE notice in the scheduler — the next one — and the hand-over to the occurrence after lived only in
the agenda's background tick, which moved on when the DAY changed. With nobody at a screen that tick runs at most
every few minutes, the first one a full period after boot; an engine woken only for the notice rings it and may sleep
again before then. Nothing is left in the scheduler, so nothing wakes it for next week: the series never rings again.

Now the pulse runs the origin's hand-over right after the delivery (`scheduler.AFTER_RUNG` → `agenda.roll_notices`),
and once when it starts; and a notice that already rang moves the series on at once, not at midnight.
Built through the product with the real scheduler; only Google is replaced.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import time

import pytest

from nucleo.pulse import loop as loop_mod, scheduler
from widgets.agenda import data as agenda, gcal

TODAY = dt.date.today()
TUE = TODAY + dt.timedelta(days=(1 - TODAY.weekday()) % 7 or 7)


@pytest.fixture(autouse=True)
def _agenda(monkeypatch):
    monkeypatch.setattr(gcal, "svc", lambda: None)                  # never his real Google Calendar
    scheduler.take_rung()
    agenda.apply_action("clear_all", {})
    yield
    agenda.apply_action("clear_all", {})
    scheduler.take_rung()


def _series() -> dict:
    agenda.apply_action("add_meeting", {"title": "Piano", "date": TUE.isoformat(), "startTime": "15:15",
                                        "endTime": "16:00", "repeat": "weekly",
                                        "until": (TUE + dt.timedelta(weeks=10)).isoformat()})
    return agenda.load_db()["meetings"][0]


def _instant(day: dt.date, hhmm: str) -> float:
    return time.mktime(time.strptime(f"{day.isoformat()} {hhmm}", "%Y-%m-%d %H:%M"))


def _ring(job_id) -> None:
    """The pulse's own firing: the job is closed, then (after the delivery) the beat's hand-over runs."""
    from memory import journal
    scheduler.mark_fired(journal.get(int(job_id)))
    asyncio.run(loop_mod.OrchestratorLoop(tick_s=1.0)._after_rung())


def test_the_next_occurrence_is_in_the_scheduler_as_soon_as_the_notice_rings():
    m = _series()
    assert m["remindFor"] == TUE.isoformat() and scheduler.next_due() == _instant(TUE, "13:15")
    _ring(m["reminder_id"])
    nxt = TUE + dt.timedelta(weeks=1)
    after = agenda.load_db()["meetings"][0]
    assert after["remindFor"] == nxt.isoformat(), "the series stayed on the occurrence that already rang"
    assert scheduler.next_due() == _instant(nxt, "13:15"), "nothing would wake the engine for next week"


def test_a_start_heals_a_series_whose_notice_rang_in_a_process_that_stopped():
    m = _series()
    from memory import journal
    scheduler.mark_fired(journal.get(int(m["reminder_id"])))     # rang, and the process stopped before handing over
    scheduler.take_rung()
    assert scheduler.next_due() is None
    asyncio.run(loop_mod.OrchestratorLoop(tick_s=1.0)._after_rung(on_load=True))
    assert scheduler.next_due() == _instant(TUE + dt.timedelta(weeks=1), "13:15")


def test_a_pending_notice_is_left_where_it_is():
    m = _series()
    assert agenda.roll_notices() is False
    assert agenda.load_db()["meetings"][0]["reminder_id"] == m["reminder_id"]
