"""The harness caps a round on DATA it already read: an empty hunt sheet, a meeting on the wrong day (audit V2-783 P1-3).

The sheet and the agenda reached the judge as prose (`judge.py`, «LA AGENDA DEL MOTOR TIENE…»), and nothing
capped a score on them: a hunt that ended with zero named rows, or a dentist appointment written a day off, could
still be graded 4/5. Two code gates now lower the verdict and name themselves, like `notice_on`; an UNREADABLE
sheet or agenda is not an empty one, and the gates stay out.
"""
from __future__ import annotations

import datetime as _dt

from tests.use_cases.e2e.agent import gates
from tests.use_cases.e2e.agent import scenarios as SC

_AT = _dt.datetime(2026, 10, 16, 12, 0).timestamp()


def _case(sid):
    return next(s for s in SC.all_scenarios() if s.id == sid)


def _verdict():
    return {"overall": 5, "scores": {"resultado": 5, "mecanismo": 5, "naturalidad": 5}, "findings": []}


def _run(mech):
    return {"transcript": [{"who": "user", "text": "hola", "at": _AT}], "mechanism_report": mech}


def test_the_hunts_and_the_dictated_meetings_declare_their_gate():
    assert _case("cheapest-monitor").rows_expected and _case("search-buy-used-car").rows_expected
    assert _case("search-buy-guitar__es").rows_expected and _case("search-buy-guitar__us").rows_expected
    assert not _case("restaurant-tonight-madrid").rows_expected
    for sid in ("dentist-appointment-into-agenda", "dentist-appointment-into-agenda__us"):
        assert _case(sid).meeting_on == "+10"


def test_an_empty_hunt_sheet_caps_the_round():
    v = gates.apply(_case("cheapest-monitor"), _run({"results_sheet": {"read": True, "n_named": 0}}), _verdict())
    assert v["overall"] <= 2 and v["scores"]["resultado"] <= 2
    assert any(f.get("gate") == "rows_on_sheet" for f in v["findings"])


def test_rows_or_an_unreadable_sheet_leave_the_verdict_alone():
    for sheet in ({"read": True, "n_named": 4}, {"read": False}):
        v = gates.apply(_case("cheapest-monitor"), _run({"results_sheet": sheet}), _verdict())
        assert v["overall"] == 5, sheet


def test_a_meeting_on_another_day_caps_the_round():
    case = _case("dentist-appointment-into-agenda")
    v = gates.apply(case, _run({"agenda_meetings": [{"title": "Dentista", "date": "2026-10-27"}]}), _verdict())
    assert v["scores"]["resultado"] <= 2 and v["overall"] <= 3
    assert v["gates"]["meeting_on"]["day"] == "2026-10-26"
    v = gates.apply(case, _run({"agenda_meetings": [{"title": "Dentista", "date": "2026-10-26"}]}), _verdict())
    assert v["overall"] == 5
    v = gates.apply(case, _run({"agenda_meetings": None}), _verdict())
    assert v["overall"] == 5 and v["gates"]["meeting_on"] == {"read": False}
