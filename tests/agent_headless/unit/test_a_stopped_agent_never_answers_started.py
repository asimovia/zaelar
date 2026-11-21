"""A request the door refuses is never answered as started (V2-852 T21, V2-854 F4, I4).

Measured on his engine (2026-11-05 15:31): with the agent stopped (⏻) a typed search got «I'm running that search
now» while `dispatch` logged the escalation REFUSED — the listener read the switch after the turn had spoken. The
errand door (`nucleo/acts/errand.escalate_to_slowbrain`, the one portal) reads `runstate.blocks_new_work` itself:
no id, no row, nothing on the bus, and its outcome — one line in his language naming the request — is said out of
turn (`pulse/say_soon`).
"""
from __future__ import annotations

import pytest

from memory import db as memdb
from nucleo import runstate
from nucleo.acts import errand
from nucleo.pulse import say_soon
from voice import trace

REQUESTS = {
    "en": "find me a used estate car, 2021 or 2022, under 120,000 km",
    "es": "búscame un piso de alquiler en Valencia con dos habitaciones",
}


@pytest.fixture
def door(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    memdb.reset_db()
    errand.reset()
    state = {"bus": [], "born": [], "stopped": True, "said": []}
    monkeypatch.setattr(errand, "_emit_bus", lambda topic, payload: state["bus"].append((topic, payload)))
    monkeypatch.setattr("nucleo.consequence.passes", lambda *a, **k: True)
    monkeypatch.setattr("nucleo.acts.surface_owner.errand_born", lambda *a, **k: None)
    monkeypatch.setattr("nucleo.circuit.ledger.born", lambda tid, req, ctx: state["born"].append(req) or f"row-{tid}")
    monkeypatch.setattr(runstate, "blocks_new_work", lambda **k: state["stopped"])
    monkeypatch.setattr(say_soon, "notify_soon", lambda text, *, key, **kw: state["said"].append((key, text)) or True)
    yield state
    trace.adopt("")
    errand.rows_settled()


@pytest.mark.parametrize("lang", ["en", "es"])
def test_a_stopped_agent_refuses_at_the_portal_and_says_so(door, monkeypatch, lang):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    trace.adopt(f"T21-{lang}")
    tid = errand.escalate_to_slowbrain(REQUESTS[lang], context={"src": "voice"})
    assert tid == 0, "a stopped agent gave the request an id"
    assert not [t for t, _p in door["bus"] if t == "escalate.requested"], "the escalation reached the bus"
    assert not door["born"], "a row was born for work that never starts"
    assert len(door["said"]) == 1, door["said"]
    key, said = door["said"][0]
    assert key.startswith("errand:refused:stopped:")
    assert said and REQUESTS[lang][:40] in said, f"the line does not name what was not started: {said!r}"
    assert "⏻" in said
    assert ("parado" in said) == (lang == "es"), "the line is not in his language"


def test_a_running_agent_still_opens_the_errand(door):
    door["stopped"] = False
    trace.adopt("T21-run")
    tid = errand.escalate_to_slowbrain(REQUESTS["en"], context={"src": "voice"})
    assert tid and [t for t, _p in door["bus"] if t == "escalate.requested"]
    assert door["born"] == [REQUESTS["en"]]
    assert not door["said"], "a started errand said a refusal"
