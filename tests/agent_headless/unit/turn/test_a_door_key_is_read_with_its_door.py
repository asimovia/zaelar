"""A verdict has three states, and a key a brief DOOR asks is never read without its door (CRIT-K2b R1, node 2.1736).

Audit of the reader table (2026-11-12 night): (a) `correction_undo` read «info is not None» as SURE — `jev.read` hands
back the info of a DOUBT too, so the owed calls ran at the licence; (b) `ask_outside_door.claimed` read the send's
backing (`errand_class`, `message_channel`) on a turn whose `portal`/`send` doors never fired, so it never launched — a
`read` faked in its own test hid it. Now `verdicts.sure` gives SURE · DOUBT · UNKNOWN, reading a door key fires its door,
and a reader that can wait awaits it. A carried copy (`brief.revived`) never fires on a read — its trip would land where
nobody reads it — so the reader that holds the reading asks and keeps it; a door whose precondition never happened (the
`call` door: its precondition is a model call) is never fired by a read. These tests run on a REAL brief handle; Jev's trip is counted.

Disarms (seen red): `sure` back to «info is not None»; no fire in `verdicts.read`; `claimed` without its wait;
the send task's channel reading without its keep; the send task's worker without its portal; the worker's exit awaiting
only `send`; a read firing the `call` door.
"""
from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace

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
    answers = Answers()
    answers.trips = []

    def trip(said, qs, question_id=""):
        answers.trips.append(sorted(qs))
        time.sleep(0.05)            # a real trip takes time: a read that does not wait reads it in flight
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
            brief_doors.landed_sync(live, door)            # its trip done before the copy's are counted
            doors.trips.clear()
            verdicts.read(tb.revived({"result": {"x": {"choice": "y", "confidence": 1.0}}, "judged": "hola"}), key, None)
            assert doors.trips == [], f"reading {key} on a carried copy paid a trip nobody reads"
    fired.clear()
    verdicts.read(_handle(), "request_type", None)
    assert fired == [], "a key the turn's own brief asks fired a door"


def test_a_claim_on_a_real_handle_awaits_the_send_doors_and_launches(doors, monkeypatch):
    """The send the reply claimed («Sending it now.», no call): the doors that back a send are asked and awaited, so the
    sure order on a leaving act becomes its task — before, the unasked doors read «no send» and nothing launched."""
    from nucleo.acts import errand
    from nucleo.request import ask_outside_door as aod
    doors[errand.CLASS_KEY] = ("sends_for_him", 0.9)
    launched = []
    monkeypatch.setattr(aod, "to_message_task", lambda wid, act, said, **k: launched.append((wid, act)) or 7)
    h = _handle({"screen_action": {"choice": "mensajeria:send_to", "confidence": 0.9},
                 "request_type": {"choice": "order", "confidence": 0.9}})
    assert asyncio.run(aod.claimed(h, "Sending it now.", "manda hola a pablo")) == 7
    assert launched == [("mensajeria", "send_to")]


@pytest.mark.parametrize("brief, reply", [
    ({"screen_action": ("mensajeria:send_to", 0.9), "request_type": ("question", 0.9)}, "Sending it now."),
    ({"screen_action": ("mensajeria:send_to", 0.9), "request_type": ("order", 0.9)}, "¿A quién se lo mando?"),
    ({"screen_action": ("musica:next", 0.9), "request_type": ("order", 0.9)}, "Done."),
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
    assert brief_doors.landed_sync(h, "call") and acts_asked.several(h) is True


def test_the_send_tasks_channel_reading_is_asked_once_and_kept(doors):
    """`send_task._reading_names` on a carried reading (off the loop): the send door is asked, awaited and KEPT in the
    reading — the next read of the same task (`send_task_answer` reads it twice) pays no second trip."""
    from nucleo.acts import message_channel
    from nucleo.request import send_task
    doors[message_channel.KEY] = ("whatsapp", 0.9)
    reading = {"result": {"request_type": {"choice": "order", "confidence": 0.9}}, "judged": "por whatsapp a pablo"}
    assert send_task._reading_names(reading, "WhatsApp") is True
    assert send_task._reading_names(reading, "whatsapp") is True
    assert len(doors.trips) == 1, f"the same task's channel paid {len(doors.trips)} trips"
    assert reading["result"][message_channel.KEY]["choice"] == "whatsapp"


def test_the_send_tasks_worker_carries_its_consent_class(doors, monkeypatch):
    """`send_task_turn.at_close` launching the worker that composes the send: its consent class is a PORTAL key, asked
    and awaited before the worker is born — unasked it travelled as None (class `none`, never parked)."""
    from nucleo.acts import errand
    from nucleo.request import send_task_turn, send_task_words
    doors[errand.CLASS_KEY] = ("sends_for_him", 0.9)
    monkeypatch.setattr(send_task_words, "by_verdict", lambda brief, **k: ("row-1", "worker"))
    born = []
    mod = SimpleNamespace(class_verdict=errand.class_verdict,
                          escalate_to_slowbrain=lambda said, context: born.append(context) or 1)
    h = _handle({"escalate": {"choice": "escalate", "confidence": 0.9}})
    got = asyncio.run(send_task_turn.at_close(h, "escribe a pablo lo del viernes", "", {"v": None}, {"v": False},
                                              lambda *a, **k: None, mod))
    assert got == "row-1" and born, "no worker was born"
    assert (born[0]["errand_class"] or {}).get("choice") == "sends_for_him", born[0]["errand_class"]


def test_the_workers_exit_awaits_the_class_that_backs_its_send(doors, monkeypatch):
    """A worker's send whose recipient the worker chose (P1-b): `backs_a_send` reads the errand class, a PORTAL key the
    commissioning turn may never have landed. The exit awaits `portal` with `send`, so a reading that asks for a send in
    his name keeps it — before, the class read unknown, as «none», and the send was dropped in silence."""
    from nucleo import on_his_behalf as ob
    from nucleo.acts import card, errand, message_channel
    from nucleo.workers import exit_gate, exit_slots, taint
    from nucleo.workers.prompts import playbook
    from widgets import contract
    doors[errand.CLASS_KEY] = ("sends_for_him", 0.9)
    doors[message_channel.KEY] = ("none", 0.9)
    inner = {"contact": "c-1", "text": "hola"}
    monkeypatch.setattr(ob, "_resolve", lambda p: ("mensajeria", "send_to", inner))
    monkeypatch.setattr(ob, "errand_words", lambda rec=None, **k: [])
    monkeypatch.setattr(ob, "shown_who", lambda *a: "Pablo")
    monkeypatch.setattr(exit_gate, "leaves", lambda *a: True)
    monkeypatch.setattr(exit_gate, "_continues_as", lambda *a: "")
    monkeypatch.setattr(exit_gate, "_emit", lambda *a: None)
    monkeypatch.setattr(playbook, "checkpoint_one", lambda rec: "")
    monkeypatch.setattr(contract, "would_refuse", lambda *a: None)
    monkeypatch.setattr(card, "licence", lambda *a, **k: SimpleNamespace(verdict="run"))
    monkeypatch.setattr(exit_slots, "read", lambda *a, **k: SimpleNamespace(inner=inner, sources={"recipient": "agent"},
                                                                           released=False))
    monkeypatch.setattr(taint, "tainted", lambda rec: False)
    reading = {"result": {"request_type": {"choice": "order", "confidence": 0.9}}, "judged": "dile a pablo que voy"}
    rec = SimpleNamespace(task_id="t-1", mandate=None, reading=reading, heard=[])
    out = exit_gate.gate(rec, {"widget_id": "mensajeria", "action": "send_to", "payload": inner})
    assert "unbacked" not in out.refused, out.refused
    assert reading["result"][errand.CLASS_KEY]["choice"] == "sends_for_him", "the exit's answer was not kept"
