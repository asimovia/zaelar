"""Who opened the turns of a switched session, and one conversation per account (node 13.39, v3.1 B2).

The proof counts, per session, the runs the manager started and what would mean another owner (the old turn stream,
the old prompt, the speech session's own commit, an effect past the gateway that is not a read). Its exit gate:
`manager_runs > 0` and those four at 0; the debug endpoint answers with it. The registry keeps ONE runtime per
account: a second session joins it, and it stops with the last.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from conversation import build
from conversation.ports import Done
from conversation.testing.fakes import AckingMouth, FakeOwed, ListTelemetry, NoMemory, RecordingTools
from conversation.testing.scripted_model import ScriptedModel, reply
from memory.db import Database
from nucleo.conversation_host import proof, sessions
from nucleo.conversation_host.clock import SystemClock
from nucleo.conversation_host.store import ZaelarStore
from tests.conversation.unit.convkit import Harness


@pytest.fixture(autouse=True)
def _fresh():
    proof._reset_for_tests()
    yield
    proof._reset_for_tests()


def test_the_manager_runs_are_counted_from_its_own_telemetry(store):
    h = Harness(store, grace=False)
    h.conv.em.port = proof.Counting(h.tel, "s1")
    h.typed("w1", 100)
    h.at(1000).pump()
    got = proof.report("s1")
    assert got["counters"]["manager_runs"] == 1 and got["passes"] and got["fails"] == []
    assert any(k == "conv_run" for k, _l, _p in h.tel.events)          # every event went on to the real port


def test_another_owner_fails_the_gate_and_names_it():
    proof.note("s2", "manager_runs")
    proof.note("s2", "livekit_turns")
    got = proof.report("s2")
    assert not got["passes"] and got["fails"] == ["livekit_turns = 1"]
    assert proof.report("s3")["fails"] == ["manager_runs = 0"] and not proof.report("s3")["on"]


def test_an_effect_past_the_gateway_is_counted():
    seen = ListTelemetry()
    c = proof.Counting(seen, "s4")
    c.emit("conv_effect", "read", {})
    c.emit("conv_effect", "refused", {})
    c.emit("conv_effect", "claimed", {})
    assert proof.report("s4")["counters"]["effects_outside_read"] == 1 and len(seen.events) == 3


def test_a_counter_that_is_not_one_is_refused():
    with pytest.raises(ValueError):
        proof.note("s5", "turns")


def test_the_endpoint_answers_with_the_report():
    from server import voice_api
    proof.note("s6", "manager_runs")
    got = json.loads(asyncio.run(voice_api.debug_conversation("s6")).body)
    assert got["passes"] and got["counters"]["manager_runs"] == 1


def test_one_runtime_per_account_a_second_session_joins_it_and_the_last_stops_it(tmp_path):
    db = Database(tmp_path / "z.db")

    def make():
        return build(account="a", owner="host", model=ScriptedModel(default=lambda ids: [reply("w9"), Done()]),
                     tools=RecordingTools(), store=ZaelarStore(db), memory=NoMemory(), clock=SystemClock(),
                     mouth=AckingMouth(), telemetry=ListTelemetry(), owed=FakeOwed())

    try:
        rt = sessions.open_("a", "desk", make, db=db)
        assert sessions.open_("a", "phone", make, db=db) is rt and sessions.get("a") is rt
        assert not sessions.close("a", "desk") and sessions.get("a") is rt      # the phone still holds it
        assert sessions.close("a", "phone") and sessions.get("a") is None
        assert not rt._thread.is_alive()
    finally:
        sessions.close_all()
        db.close()
