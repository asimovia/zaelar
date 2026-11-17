"""A verdict has three states, and a key a brief DOOR asks is never read without its door (CRIT-K2b R1, node 2.1736).

Audit of the reader table (2026-11-12 night): (a) `correction_undo` read «info is not None» as SURE — `jev.read` hands
back the info of a DOUBT too, so the owed calls ran at the licence; (b) `ask_outside_door.claimed` read the send's
backing (`errand_class`, `message_channel`) on a turn whose `portal`/`send` doors never fired, so it never launched — a
`read` faked in its own test hid it. Now `verdicts.sure` gives SURE · DOUBT · UNKNOWN, reading a door key fires its door,
and a reader that can wait awaits it. A carried copy (`brief.revived`) never fires on a read — its trip would land where
nobody reads it — so the reader that holds the reading asks and keeps it; a door whose precondition never happened (the
`call` door: its precondition is a model call) is never fired by a read. These tests run on a REAL brief handle; Jev's trip is counted.

Disarms (seen red): `sure` back to «info is not None»; no fire in `verdicts.read`; a read firing the `call` door.
"""
from __future__ import annotations

import asyncio
import threading
import time

import pytest

from nucleo.turn import brief as tb, brief_doors, verdicts


def _handle(result: dict | None = None, said: str = "manda hola a pablo") -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": dict(result or {}), "judged": said, "turn_id": "t-doors", "open_ids": []}


@pytest.fixture
def doors(monkeypatch):
    """Jev on, its door trip answered by `answers` (key → (choice, confidence)) — no network; `answers.trips` counts."""
    from nucleo import jev

    class Answers(dict):
        trips: list = []
        delay = 0.05                # a real trip takes time: a read that does not wait reads it in flight
    answers = Answers()
    answers.trips = []

    def trip(said, qs, question_id=""):
        answers.trips.append(sorted(qs))
        time.sleep(answers.delay)
        return {k: {"choice": c, "confidence": p, "probs": {}} for k, (c, p) in answers.items() if k in qs}
    monkeypatch.setattr(jev, "enabled", lambda: True)
    monkeypatch.setattr(jev, "choose_many_sync", trip)
    return answers


def test_a_verdict_has_three_states_and_a_doubt_is_never_sure():
    h = _handle({"x_key": {"choice": "another", "confidence": 0.6}})
    assert verdicts.sure(h, "x_key", verdicts.VETO) == (verdicts.DOUBT, None), "a 0.6 doubt read as sure at VETO"
    assert verdicts.sure(h, "x_key", 0.5) == (verdicts.SURE, "another")
    assert verdicts.sure(h, "missing_key", 0.5) == (verdicts.UNKNOWN, None)
    assert verdicts.sure(None, "x_key", 0.5) == (verdicts.UNKNOWN, None)


def test_reading_any_door_key_fires_its_door_but_never_on_a_carried_copy(doors, monkeypatch):
    real, fired = brief_doors.fire, []
    monkeypatch.setattr(brief_doors, "fire", lambda h, door, **k: (door and fired.append(door), real(h, door, **k))[1])
    for door in brief_doors.DOORS:
        for key in brief_doors.keys(door):
            fired.clear()
            verdicts.read(live := _handle(), key, None)
            assert fired == [door], f"reading {key} left its door {door!r} unasked"
            if door == "call":            # its precondition is a model call: a read only reads what the call asked
                assert "call" not in (live.get("_doors") or {}), "a read paid the call door's trip"
                continue
            asyncio.run(brief_doors.landed(live, door))    # its trip done before the copy's are counted
            doors.trips.clear()
            verdicts.read(tb.revived({"result": {"x": {"choice": "y", "confidence": 1.0}}, "judged": "hola"}), key, None)
            assert doors.trips == [], f"reading {key} on a carried copy paid a trip nobody reads"
    fired.clear()
    verdicts.read(_handle(), "request_type", None)
    assert fired == [], "a key the turn's own brief asks fired a door"


@pytest.mark.parametrize("brief, reply", [
    ({"screen_action": ("mensajeria:send_to", 0.9), "request_type": ("question", 0.9)}, "Sending it now."),
    ({"screen_action": ("mensajeria:send_to", 0.9), "request_type": ("order", 0.9)}, "¿A quién se lo mando?"),
    ({"screen_action": ("musica:next", 0.9), "request_type": ("order", 0.9)}, "Done."),
    ({"screen_action": ("mensajeria:send_to", 0.3), "request_type": ("order", 0.7)}, "Done."),   # neither branch
])
def test_a_close_that_cannot_claim_a_send_pays_no_trip(doors, brief, reply):
    """Both branches of `claimed` need an order and a turn that does not ask, on an act that leaves: no other close waits."""
    from nucleo.request import ask_outside_door as aod
    h = _handle({k: {"choice": c, "confidence": p} for k, (c, p) in brief.items()})
    assert asyncio.run(aod.claimed(h, reply, "manda hola a pablo")) == 0
    assert doors.trips == [], "a close that cannot claim a send asked the send's doors"


def test_several_acts_is_read_only_once_a_model_call_fired_its_door(doors):
    """The route and the reply read `acts_asked.several` on turns with no model call: firing the `call` door there would
    pay a trip nobody waits for; unasked it reads «not sure». Once the call fired it, the read is the door's answer."""
    from nucleo.turn import acts_asked
    doors[acts_asked.KEY] = (acts_asked.SEVERAL, 0.95)
    h = _handle()
    assert acts_asked.several(h) is False and doors.trips == []
    assert asyncio.run(brief_doors.landed(h, "call")) and acts_asked.several(h) is True


def test_a_door_that_cannot_fire_never_blinds_the_reading(monkeypatch):
    """P3: the door's fire lives in its own `try` — a broken door table still reads what the brief holds."""
    def broken(_key):
        raise ImportError("a door module that cannot load")
    monkeypatch.setattr(brief_doors, "door_of", broken)
    h = _handle({"request_type": {"choice": "order", "confidence": 0.9}})
    assert verdicts.read(h, "request_type", None)[0] == "order"
