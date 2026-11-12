"""A correction onto the OTHER row is one unit: the move back and the same move on the other row (2026-11-12).

Multi-turn bench, «no, perdona, la otra, la de las cinco — la de las diez déjala como estaba», 3 of 4 in Spanish: the
model wrote ONLY the move back of the 10:00 (which is the undo itself), never the move of the 17:00, and the mouth said
«Listo.» over a calendar that still held the 17:00. The undo at the door (2.1725) only ran when the model named the
other row. Now the correcting act is recorded at the door, a door question asks which kind of correction it is
(`correction_kind`, asked only on such a turn), and once the turn's acts landed the card's END STATE says what is still
owed (`agenda.correction_owed`): on a sure «another item» it runs through the same door; when the card cannot name
the other row, or the verdict is not sure enough to act, the mouth says only part was done — never «Done.».

Disarm: `complete` owing nothing, the other row's move dropped from `correction_owed`, the put-back guard of
`undo_of`, the «part only» outcome → each red.
"""
from __future__ import annotations

import asyncio
import datetime as dt

import pytest

from nucleo.circuit import verdict as V
from nucleo.turn import brief_doors, verdicts
from widgets.agenda import data as agenda, edit, gcal, reminders

DAY = (dt.date.today() + dt.timedelta(days=1)).isoformat()
TODAY = dt.date.today().isoformat()
T = "Meeting with Mark"
FIRST = {"title": T, "date": DAY, "currentTime": "10:00", "newTime": "12:00"}


@pytest.fixture(autouse=True)
def _agenda(monkeypatch):
    monkeypatch.setattr(gcal, "svc", lambda: None)
    for mod in (agenda, reminders):
        monkeypatch.setattr(mod, "_schedule_reminder", lambda *a, **k: ("job", ""))
        monkeypatch.setattr(mod, "_cancel_reminder", lambda m: None)
    from widgets import store
    db = agenda.load_db()
    db["meetings"] = [m for m in db.get("meetings") or [] if T not in str(m.get("title") or "")]
    store.save(agenda.WIDGET_ID, db)
    for start, end in (("10:00", "11:00"), ("17:00", "18:00")):
        assert agenda.apply_action("add_meeting", {"title": T, "date": DAY, "startTime": start, "endTime": end}).get("ok") is not False
    db = agenda.load_db()
    db.pop("focus", None)
    store.save(agenda.WIDGET_ID, db)
    assert agenda.apply_action("move_meeting", FIRST).get("ok") is not False      # his first turn: the 10:00 → 12:00


def _rows() -> list[str]:
    return sorted(f"{m['date']} {m['startTime']}" for m in agenda.load_db()["meetings"] if T in m.get("title", ""))


def _move(**pl) -> dict:
    return agenda.apply_action("move_meeting", {"title": T, "date": DAY, **pl})


def _run(owed):
    for act, pl in (owed or {}).get("calls") or []:
        assert agenda.apply_action(act, pl).get("ok") is not False, (act, pl)


def test_the_end_state_says_what_the_correction_still_owes():
    owed = agenda.correction_owed("move_meeting", FIRST)
    assert len(owed["calls"]) == 2 and not owed["open"], owed      # nothing done yet: the move back AND the other
    _run(owed)
    assert _rows() == [f"{DAY} 10:00", f"{DAY} 12:00"]
    assert agenda.correction_owed("move_meeting", FIRST) == {"calls": [], "open": []}   # whole: nothing owed


def test_after_the_models_move_back_only_the_other_row_is_owed():
    _move(currentTime="12:00", newTime="10:00")                    # the model's ONLY call: the undo
    owed = agenda.correction_owed("move_meeting", FIRST)
    assert owed["calls"] == [("move_meeting", {"title": T, "date": DAY, "currentTime": "17:00", "newDate": DAY,
                                               "newTime": "12:00"})], owed
    _run(owed)
    assert _rows() == [f"{DAY} 10:00", f"{DAY} 12:00"]


def test_the_other_row_sent_to_a_wrong_day_is_moved_from_where_it_sits():
    _move(currentTime="12:00", newTime="10:00")
    _move(currentTime="17:00", newDate=TODAY, newTime="12:00")    # a wrong call: the right row, the wrong day
    _run(agenda.correction_owed("move_meeting", FIRST))
    assert _rows() == [f"{DAY} 10:00", f"{DAY} 12:00"], _rows()


def test_two_candidates_for_the_other_row_are_not_guessed():
    agenda.apply_action("add_meeting", {"title": T, "date": DAY, "startTime": "19:00", "endTime": "20:00"})
    owed = agenda.correction_owed("move_meeting", FIRST)
    assert owed["open"] == ["17:00", "19:00"] and len(owed["calls"]) == 1, owed    # the move back only


def test_a_move_already_put_back_is_not_undone_again():
    """The model's move back landed first: the newest moved row is now the 10:00 (its `movedFrom` says 12:00), and the
    old undo would have moved it to 12:00 again on the next call."""
    _move(currentTime="12:00", newTime="10:00")
    assert edit.undo_of("move_meeting", FIRST, {"title": T, "date": DAY, "currentTime": "17:00", "newTime": "12:00"}) is None


@pytest.fixture
def turn(monkeypatch):
    from nucleo import done_ops
    from nucleo.acts import correction_undo as cu
    from nucleo.request import stop
    from voice import trace as _trace
    cu.reset()
    st = {"choice": cu.ANOTHER, "conf": 0.93}
    monkeypatch.setattr(stop, "corrected_card", lambda brief: "agenda")
    monkeypatch.setattr(done_ops, "his_last", lambda *a, **k: {"wid": "agenda", "action": "move_meeting",
                                                               "payload": FIRST, "trace": "t-before", "at": 1.0})
    monkeypatch.setattr(_trace, "current", lambda: "t-now")
    monkeypatch.setattr(brief_doors, "fire", lambda h, door: st.setdefault("fired", door) and None)

    async def landed(*_a, **_k):
        return True
    monkeypatch.setattr(brief_doors, "landed", landed)
    monkeypatch.setattr(verdicts, "read", lambda h, key, fb, min_confidence=None:
                        (st["choice"], {"confidence": st["conf"]})
                        if key == cu.KEY and st["conf"] >= (min_confidence or verdicts.LICENCE) else (fb, None))
    ran = []

    def door(wid, act, pl):
        if cu.undo_first(wid, act, pl, {}, apply=door) == cu.ALREADY:
            return None
        ran.append(pl)
        return agenda.apply_action(act, pl)
    return cu, st, door, ran


def test_a_sure_correction_finishes_what_the_model_left(turn):
    cu, st, door, ran = turn
    door("agenda", "move_meeting", {"title": T, "date": DAY, "currentTime": "12:00", "newTime": "10:00"})
    assert st.get("fired") == "correct", "the door question is asked on the correcting turn"
    assert asyncio.run(cu.complete(())) == []
    assert _rows() == [f"{DAY} 10:00", f"{DAY} 12:00"], _rows()
    assert asyncio.run(cu.complete(())) == [], "once per turn"


def test_a_correction_not_sure_enough_to_act_says_part_only(turn):
    cu, st, door, _ran = turn
    st["conf"] = 0.7
    door("agenda", "move_meeting", {"title": T, "date": DAY, "currentTime": "12:00", "newTime": "10:00"})
    out = asyncio.run(cu.complete(()))
    assert len(out) == 1 and out[0].verdict == V.UNMET.name and out[0].card == "agenda", out
    assert _rows() == [f"{DAY} 10:00", f"{DAY} 17:00"], "nothing moved without a sure verdict"


def test_an_undo_only_or_a_different_change_owes_nothing(turn):
    cu, st, door, _ran = turn
    for kind in (cu.UNDO_ONLY, cu.SAME):
        cu.reset()
        st["choice"] = kind
        door("agenda", "move_meeting", {"title": T, "date": DAY, "currentTime": "12:00", "newTime": "10:00"})
        assert asyncio.run(cu.complete(())) == []
        assert _rows() == [f"{DAY} 10:00", f"{DAY} 17:00"]
        _move(currentTime="10:00", newTime="12:00")


def test_when_the_model_named_the_other_row_the_door_already_made_it_whole(turn):
    cu, _st, door, ran = turn
    door("agenda", "move_meeting", {"title": T, "date": DAY, "currentTime": "17:00", "newTime": "12:00"})
    assert _rows() == [f"{DAY} 10:00", f"{DAY} 12:00"] and len(ran) == 2, (ran, _rows())
    assert asyncio.run(cu.complete(())) == []
    assert _rows() == [f"{DAY} 10:00", f"{DAY} 12:00"]


def test_the_question_belongs_to_its_door():
    from nucleo.acts import correction_undo as cu
    assert brief_doors.door_of(cu.KEY) == "correct"
    q = cu.question()
    assert q is None or set(q["criteria"]) == {cu.ANOTHER, cu.SAME, cu.UNDO_ONLY}

