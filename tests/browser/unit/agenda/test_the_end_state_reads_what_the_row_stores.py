"""V2-886 fila 5 — an agenda call's end state is rendered over the values the card STORES, never his raw words, and a
routed act owes the end state of the act that ran. Measured 2026-11-11 (scratch store): a move to «jueves» / «a las 8
de la tarde» landed and its spec `date=jueves` / `startTime=a las 8…` judged it unmet — «could not be completed» over
a move that had happened; an `update_meeting` with a new hour was judged by an `update_meeting` write the move never
noted. Disarm: `spec.render` without `_card_call` → red."""
import pytest

from nucleo.circuit import spec
from widgets.agenda import when


def _clause(done_when, collection):
    return next(c for c in done_when["all"] if c["collection"] == collection)


@pytest.mark.parametrize("day,hour,hhmm", [("jueves", "a las 8 de la tarde", "20:00"), ("thursday", "8 pm", "20:00"),
                                           ("el jueves", "20:00", "20:00")])
def test_a_move_in_his_words_is_judged_by_the_stored_values(day, hour, hhmm, monkeypatch):
    monkeypatch.setattr(spec._baseline, "snapshot", lambda dw: None)
    dw = spec.render("agenda", "move_meeting", {"title": "Padel", "newDate": day, "newTime": hour})
    row = _clause(dw, "meetings")["where"]
    assert row["date"] == when._resolve_date(day, at=hhmm) and row["date"][:2] == "20", row
    assert row["startTime"] == hhmm


def test_an_add_on_a_named_day_is_judged_on_the_day_the_act_writes(monkeypatch):
    monkeypatch.setattr(spec._baseline, "snapshot", lambda dw: None)
    dw = spec.render("agenda", "add_meeting", {"title": "Football game", "date": "wednesday", "startTime": "12:00"})
    assert _clause(dw, "meetings")["where"]["date"] == when._resolve_date("wednesday", at="12:00")


def test_an_edit_that_carries_a_when_owes_the_moves_end_state(monkeypatch):
    monkeypatch.setattr(spec._baseline, "snapshot", lambda dw: None)
    dw = spec.render("agenda", "update_meeting", {"title": "Padel", "startTime": "19:00"})
    assert _clause(dw, "writes")["where"]["action"] == "move_meeting"
    plain = spec.render("agenda", "update_meeting", {"title": "Padel", "newTitle": "Pádel con Ana"})
    assert _clause(plain, "writes")["where"]["action"] == "update_meeting"
