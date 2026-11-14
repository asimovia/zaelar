#
# test_a_period_is_read_day_by_day.py — demo pass 34 (2026-09-29), R3.
#
# «find me five days in her vacation where i'm free and tell me the dates» — the model read the agenda for
# «What meetings does Richard have between December 20, 2026 and January 4, 2027?». Neither date was understood
# (only ISO dates and today/tomorrow were), so the read fell back to the next eight appointments, all in
# September, and the answer was «I can't honestly confirm you're free on any of those days». A period is
# answered as a period: every day between its ends, which ones have an hour taken, and the all-day rows once.
#
import pytest

from widgets.agenda import data as agenda_data
from widgets.agenda import query

_MEETINGS = [
    {"id": "1", "title": "ZAELAR weekly review", "date": "2026-09-30", "startTime": "09:00", "endTime": "09:30"},
    {"id": "2", "title": "Dentist", "date": "2026-12-22", "startTime": "10:00", "endTime": "11:00"},
    {"id": "3", "title": "Anna's vacation", "date": "2026-12-20", "allDay": True,
     "repeat": {"freq": "daily", "until": "2027-01-04"}},
]


@pytest.fixture(autouse=True)
def _calendar(monkeypatch):
    monkeypatch.setattr(agenda_data, "load_db", lambda: {"meetings": [dict(m) for m in _MEETINGS]})
    monkeypatch.setattr(query, "_today", lambda: "2026-09-29")


@pytest.mark.parametrize("question", [
    "What meetings does Richard have between December 20, 2026 and January 4, 2027?",
    "¿Qué citas tiene entre el 20 de diciembre de 2026 y el 4 de enero de 2027?",
    "meetings from 2026-12-20 to 2027-01-04",
])
def test_a_period_is_answered_with_every_day_in_it(question):
    out = query.read_query(question)
    assert "2026-12-20" in out and "2027-01-04" in out
    assert "Periodo" in out, out
    free = out.split("Días SIN ninguna cita con hora")[1].split("\n")[0]
    assert "2026-12-21" in free and "2026-12-23" in free
    assert "2026-12-22" not in free, "the dentist's day was listed as free"
    assert "Dentist" in out and "Anna's vacation" in out
    assert "ZAELAR weekly review" not in out, "an appointment outside the period leaked in"


def test_a_month_word_with_no_day_next_to_it_is_not_a_date():
    assert query._dates_in("Richard may have 2 meetings") == []


def test_a_single_day_keeps_its_own_record():
    out = query.read_query("What do I have on 2026-09-30?")
    assert "Periodo" not in out and "ZAELAR weekly review" in out


# Desktop, 2026-11-14: «semana que viene, ¿qué tengo que hacer?» resolved no date and matched no row, so the read
# answered nothing and the reply was built from today's summary («solo veo las citas de hoy»). A question that places
# no day and names nothing the calendar holds is handed the coming days, dated, to the end of next month; the turn
# places the period against them and its dated day list (CRIT-C4e). No period word is read by the door.
# Disarm: `_coming` returning "" → red.
_SOON = [
    {"id": "p", "title": "Notario", "date": "2026-11-02", "startTime": "09:00"},
    {"id": "t", "title": "Fútbol", "date": "2026-11-14", "startTime": "12:00"},
    {"id": "w", "title": "Dentist", "date": "2026-11-18", "startTime": "10:00"},
    {"id": "m", "title": "Cena de empresa", "date": "2026-12-12", "startTime": "21:00"},
    {"id": "f", "title": "Reyes", "date": "2027-01-06", "startTime": "10:00"},
]


@pytest.mark.parametrize("question", [
    "semana que viene, ¿qué tengo que hacer?", "¿qué tengo este fin de semana?", "¿y el mes que viene?",
    "what do I have next week?", "anything on this weekend?", "and next month?",
])
def test_a_period_he_names_by_words_is_read_as_the_coming_days(monkeypatch, question):
    monkeypatch.setattr(agenda_data, "load_db", lambda: {"meetings": [dict(m) for m in _SOON]})
    monkeypatch.setattr(query, "_today", lambda: "2026-11-14")
    out = query.read_query(question)
    assert "Periodo 2026-11-14 → 2026-12-31" in out, out
    assert "Dentist" in out and "Cena de empresa" in out and "Fútbol" in out
    assert "Notario" not in out and "Reyes" not in out, "a day outside the coming period leaked in"
    free = out.split("Días SIN ninguna cita con hora")[1].split("\n")[0]
    assert "2026-11-17" in free and "2026-11-18" not in free


def test_a_subject_it_holds_still_answers_with_its_row(monkeypatch):
    monkeypatch.setattr(agenda_data, "load_db", lambda: {"meetings": [dict(m) for m in _SOON]})
    monkeypatch.setattr(query, "_today", lambda: "2026-11-14")
    out = query.read_query("¿cuándo fue lo del notario?")
    assert "Notario" in out and "Periodo" not in out
