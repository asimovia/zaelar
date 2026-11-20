"""A standalone notice reads the card's own day and hour.

Measured on a text session (2026-11-16): «Remind me tomorrow at 8am to water the plants, and on Friday at 5pm to call
the bank.» → two `add_reminder {title, date, time}` calls — the slots every other write of the card declares — and
the door refused both for a missing `notice_at`; the mouth then told him to «add a notice_at value». A day and an hour
ARE the instant and a title IS what to tell him (`notice.in_the_cards_shape`); words are still not a slot.
"""
from __future__ import annotations

import datetime as dt
import importlib
import pathlib

import pytest

from widgets.agenda import notice

FAR = (dt.date.today() + dt.timedelta(days=40)).isoformat()


def _door(payload, _scheduler_never_touches_the_live_journal):
    r = notice._a_add_reminder("add_reminder", payload, {}, {})
    return r, list(_scheduler_never_touches_the_live_journal.values())


@pytest.mark.parametrize("payload, hour, told", [
    ({"title": "Water the ferns", "date": FAR, "time": "08:00"}, "08:00", "Water the ferns"),
    ({"title": "llamar a la gestoría", "date": FAR, "startTime": "17:30"}, "17:30", "llamar a la gestoría"),
    ({"commitment": "renew the passport", "date": FAR}, notice.DAY_HOUR, "renew the passport"),   # a day, no hour
])
def test_a_day_and_an_hour_are_the_instant(payload, hour, told, _scheduler_never_touches_the_live_journal):
    r, jobs = _door(payload, _scheduler_never_touches_the_live_journal)
    assert r.get("ok") and r.get("verdict") == "met", r
    assert jobs and jobs[-1]["schedule"] == f"{FAR} {hour}" and told in jobs[-1]["prompt"], jobs


def test_a_day_said_by_its_name_is_resolved_by_the_cards_own_reader(_scheduler_never_touches_the_live_journal):
    r, jobs = _door({"title": "feed the cat", "date": "tomorrow", "time": "07:15"},
                    _scheduler_never_touches_the_live_journal)
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    assert r.get("ok") and jobs[-1]["schedule"] == f"{tomorrow} 07:15", (r, jobs)


def test_the_declared_slot_still_wins(_scheduler_never_touches_the_live_journal):
    r, jobs = _door({"notice_at": f"{FAR} 10:00", "date": "tomorrow", "time": "07:15", "commitment": "x"},
                    _scheduler_never_touches_the_live_journal)
    assert r.get("ok") and jobs[-1]["schedule"] == f"{FAR} 10:00"


def test_no_day_and_no_hour_still_asks(_scheduler_never_touches_the_live_journal):
    r, jobs = _door({"title": "water the ferns"}, _scheduler_never_touches_the_live_journal)
    assert r.get("ok") is False and r.get("verdict") == "asked" and not jobs, "a moment is never guessed"


def test_disarmed_the_cards_shape_is_refused_again(_scheduler_never_touches_the_live_journal):
    src = pathlib.Path(notice.__file__)
    original = src.read_text(encoding="utf-8")
    reader = "    p = in_the_cards_shape(payload)\n"
    assert reader in original, "the door no longer reads the card's shape where this disarm expects it"
    try:
        src.write_text(original.replace(reader, "    p = payload if isinstance(payload, dict) else {}\n"),
                       encoding="utf-8")
        mutated = importlib.reload(notice)
        r = mutated._a_add_reminder("add_reminder", {"title": "x", "date": FAR, "time": "08:00"}, {}, {})
        assert r.get("ok") is False, "the mutation did not land"
    finally:
        src.write_text(original, encoding="utf-8")
        for pyc in (src.parent / "__pycache__").glob("notice.*.pyc"):
            pyc.unlink()
        importlib.reload(notice)
    assert notice._a_add_reminder("add_reminder", {"title": "x", "date": FAR, "time": "08:00"}, {}, {}).get("ok")


# ── audit 2026-11-17: a slot that is not a day or an hour is not read as one, and an assumed one never lands behind ──

AT_THREE = dt.datetime.combine(dt.date.today(), dt.time(15, 0))
TODAY = dt.date.today().isoformat()


@pytest.mark.parametrize("day, hour", [
    ("", "8am"),                 # no day, and the hour is gone today: five minutes from now is not what he asked
    ("today", ""),               # no hour, and the card's own hour for a day is gone
    ("", "in 2 hours"),          # not an hour
    ("", "after lunch"),
    ("next month", ""),          # not a day this reader knows: never today
    ("when the plumber leaves", "08:00"),
    (FAR, "25:00"),
])
def test_what_is_not_a_day_or_an_hour_asks(day, hour):
    assert notice.instant_of(day, hour, AT_THREE) == "", "a moment was assumed"


@pytest.mark.parametrize("day, hour, at", [
    ("", "17h", f"{TODAY} 17:00"), ("", "17h30", f"{TODAY} 17:30"), ("", "5 p.m.", f"{TODAY} 17:00"),
    ("", "23:30", f"{TODAY} 23:30"), (FAR, "12am", f"{FAR} 00:00"), (f"{FAR}T08:00", "", f"{FAR} 08:00"),
    (FAR, "", f"{FAR} {notice.DAY_HOUR}"),
])
def test_a_day_or_an_hour_still_ahead_is_the_instant(day, hour, at):
    assert notice.instant_of(day, hour, AT_THREE) == at


def test_the_door_asks_in_its_own_words_and_schedules_nothing(_scheduler_never_touches_the_live_journal, monkeypatch):
    r, jobs = _door({"title": "feed the cat", "date": "next month"}, _scheduler_never_touches_the_live_journal)
    assert r.get("ok") is False and r.get("verdict") == "asked" and not jobs, (r, jobs)
    from nucleo.request import refusal_line
    for lang in ("en", "es"):
        monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
        said = refusal_line.speakable("agenda", r)
        assert said and "?" in said and "notice_at" not in said and said != r["error"], said


def test_disarmed_an_unread_day_is_today_again():
    src = pathlib.Path(notice.__file__)
    original = src.read_text(encoding="utf-8")
    strict = "    d = _when._read_date(day, hh) if day else _when._today()\n"
    assert strict in original, "the strict reading is not where this disarm expects it"
    try:
        src.write_text(original.replace(strict, "    d = _when._resolve_date(day, hh)\n"), encoding="utf-8")
        mutated = importlib.reload(notice)
        assert mutated.instant_of("next month", "23:59", AT_THREE) == f"{TODAY} 23:59", "the mutation did not land"
    finally:
        src.write_text(original, encoding="utf-8")
        for pyc in (src.parent / "__pycache__").glob("notice.*.pyc"):
            pyc.unlink()
        importlib.reload(notice)
    assert notice.instant_of("next month", "23:59", AT_THREE) == ""
