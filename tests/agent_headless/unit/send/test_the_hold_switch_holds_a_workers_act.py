"""The outbound switch holds a worker's act at its exit door, before any question (contention M1, node 5.77).

`nucleo/workers/exit_gate.gate` asks the one exit door (`connectors/exit.check`) after the act's own refusal and before
anything else: lane `mandate` when an errand's mandate covers the channel, else `worker`. Held → the act is refused
with the reason and nothing is asked. Not held, and the act PASSES (a mandate, a type declared harmless, his order over
a draft he saw) → the call carries its lane stamped by code (`exit.Stamp` under `_lane`). An act that is still to be
asked carries none: that payload is kept for his yes. Without the variable the door behaves as before.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from connectors import exit as door

SEND = {"widget_id": "mensajeria", "action": "send_to",
        "payload": {"contact": "Odile Varga", "text": "I am late", "platform": "whatsapp"}}
MANDATE = {"parties": ["c1"], "channels": ["whatsapp"], "may": ["message"]}


@pytest.fixture
def world(tmp_path, monkeypatch):
    from nucleo import consent, his_words, untrusted
    from nucleo.workers.prompts import playbook
    from widgets import contract, store
    from widgets.contactos import data as cd
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    monkeypatch.setattr(consent, "_overrides_path", lambda: tmp_path / "consent.json")
    monkeypatch.delenv(door.ENV, raising=False)
    consent._reset_for_tests()
    cd.apply_action("add_contact", {"name": "Odile Varga", "phone": "611 204 377"})
    monkeypatch.setattr(playbook, "checkpoint_one", lambda rec: "")
    monkeypatch.setattr(contract, "would_refuse", lambda *a, **k: None)
    untrusted.reset()
    his_words.reset()
    door._reset_counters()

    def rec(mandate=None):
        return SimpleNamespace(task_id="t1", playbook_chosen="message", uid="t1", started=time.time(), depth=0,
                               trace_id="", surface="", sheet="", mandate=mandate or {}, reading=None,
                               heard=["send a whatsapp to Odile saying I am late"], own_words=True)
    yield SimpleNamespace(rec=rec)
    consent._reset_for_tests()
    untrusted.reset()
    his_words.reset()


def _gate(rec):
    from nucleo.workers import exit_gate
    return exit_gate.gate(rec, {**SEND, "payload": dict(SEND["payload"])})


def test_without_the_switch_a_send_still_to_be_asked_carries_no_lane(world):
    ex = _gate(world.rec())
    assert ex.question and not ex.refused, ex
    assert "_lane" not in ex.payload["payload"], "the payload kept for his yes carries no stamp"


def test_without_the_switch_a_mandated_send_passes_stamped_with_the_mandate_lane(world):
    ex = _gate(world.rec(MANDATE))
    assert ex.verdict == "pass", ex
    lane = ex.payload["payload"]["_lane"]
    assert isinstance(lane, door.Stamp) and door.stamped(lane) == door.MANDATE


def test_without_the_switch_an_act_harmless_by_its_type_passes_stamped_with_the_worker_lane(world, monkeypatch):
    from nucleo.workers import exit_gate
    monkeypatch.setattr(exit_gate, "asks_by_itself", lambda *a, **k: False)
    ex = _gate(world.rec())
    assert ex.released and not ex.question, ex
    lane = ex.payload["payload"]["_lane"]
    assert isinstance(lane, door.Stamp) and door.stamped(lane) == door.WORKER


@pytest.mark.parametrize("mandate", [None, MANDATE])
def test_with_the_switch_on_a_workers_send_is_held_and_nothing_is_asked(world, monkeypatch, mandate):
    monkeypatch.setenv(door.ENV, "all")
    ex = _gate(world.rec(mandate))
    assert ex.refused and not ex.question, ex
    assert "held" in ex.refused and "nothing was sent" in ex.refused
    assert "_lane" not in ex.payload["payload"], "a held act carries no lane: it is not going anywhere"
    lane = door.MANDATE if mandate else door.WORKER
    assert door.counters().get(f"mensajeria:send_to/{lane}/held") == 1, door.counters()


def test_holding_only_the_mandate_lane_holds_the_mandated_send_and_still_asks_the_other(world, monkeypatch):
    monkeypatch.setenv(door.ENV, "mandate")
    assert _gate(world.rec(MANDATE)).refused
    ex = _gate(world.rec())
    assert ex.question and not ex.refused


def test_an_act_that_does_not_leave_is_untouched_by_the_switch(world, monkeypatch):
    from nucleo.workers import exit_gate
    monkeypatch.setenv(door.ENV, "all")
    call = {"widget_id": "agenda", "action": "add_meeting", "payload": {"title": "Dentist"}}
    ex = exit_gate.gate(world.rec(), call)
    assert ex.verdict == "pass" and ex.payload == call
