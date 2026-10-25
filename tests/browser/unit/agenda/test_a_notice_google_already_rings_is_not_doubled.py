"""A notice Google Calendar already rings for is not rung a second time by the agent (V2-796, node 2.801).

The operator's rule (2026-10-25): «si colocamos algo en Google Calendar y Google Calendar ya avisa al usuario, no
tenemos que lanzar un aviso desde el propio agente». Asked at FIRE time from what Google said about the event, and
only for the DEFAULT notice: one he asked for is always ours (CRIT-C4c). An unknown alarm state rings — a notice too
many is better than a lost one.
"""
from __future__ import annotations

from connectors.calendar import google_calendar as gc
from widgets.agenda import reminders


def _db(meeting: dict, alarms=True) -> dict:
    return {"meetings": [meeting], "google": {"calendars": [{"id": "primary", "alarms": alarms}]}}


def _g(**kw) -> dict:
    return {"title": "Dentista", "date": "2026-11-03", "startTime": "17:00", "reminder_id": "42",
            "source": "google", "googleCalendarId": "primary", **kw}


def test_what_google_says_about_an_event_is_read():
    assert gc.reminders_mode({}) == "default", "no reminders object = the calendar's defaults (Google's own default)"
    assert gc.reminders_mode({"reminders": {"useDefault": True}}) == "default"
    assert gc.reminders_mode({"reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 10}]}}) == "popup"
    assert gc.reminders_mode({"reminders": {"useDefault": False, "overrides": [{"method": "email", "minutes": 60}]}}) == "none"
    assert gc.reminders_mode({"reminders": {"useDefault": False}}) == "none"
    ev = {"id": "x", "summary": "Dentista", "start": {"dateTime": "2026-11-03T17:00:00+01:00"},
          "end": {"dateTime": "2026-11-03T18:00:00+01:00"}, "reminders": {"useDefault": True}}
    assert gc.event_to_meeting(ev, "primary")["googleReminders"] == "default"


def test_a_google_alarm_covers_the_default_notice():
    assert reminders.covered_by("42", _db(_g(googleReminders="popup"))) == "google"
    assert reminders.covered_by("42", _db(_g(googleReminders="default"), alarms=True)) == "google"


def test_no_google_alarm_means_the_agent_rings():
    assert reminders.covered_by("42", _db(_g(googleReminders="default"), alarms=False)) == ""
    assert reminders.covered_by("42", _db(_g(googleReminders="none"))) == ""
    assert reminders.covered_by("42", _db(_g(googleReminders=""))) == "", "unknown is ours"
    assert reminders.covered_by("42", {"meetings": [_g(googleReminders="default")], "google": {"calendars": []}}) == ""


def test_an_asked_notice_is_always_ours():
    assert reminders.covered_by("42", _db(_g(googleReminders="popup", remindAsked=True))) == ""


def test_a_local_appointment_is_always_ours():
    local = {"title": "ITV", "date": "2026-11-05", "reminder_id": "42", "googleReminders": "popup"}
    assert reminders.covered_by("42", _db(local)) == ""


def test_the_calendar_list_says_whether_it_rings():
    class R:
        status_code = 200
        def json(self):
            return {"items": [{"id": "a", "defaultReminders": [{"method": "popup", "minutes": 10}]},
                              {"id": "b", "defaultReminders": [{"method": "email", "minutes": 10}]},
                              {"id": "c"}]}

    class C:
        def get(self, *a, **k):
            return R()
    cals = {c["id"]: c["alarms"] for c in gc.list_calendars(C(), "https://x", "t")["calendars"]}
    assert cals == {"a": True, "b": False, "c": False}
