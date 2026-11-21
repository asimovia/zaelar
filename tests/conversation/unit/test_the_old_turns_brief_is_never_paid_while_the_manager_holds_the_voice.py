"""The old turn's brief is never paid while the manager holds the voice (node 13.113, V2-941, plan v3.2 C18).

The operator's session c2cb9f47 showed ten `jev turn-brief` calls in a session of the manager: the old turn's eager
brief, wired into the speech session's STT, fired on every eager end of turn the provider sent, and its verdict was
read by nobody — one model call each time. Now:

  · the eager end of turn fires nothing while a voice session of the manager holds the voice; switched off (the host
    not loaded) or with no such session it fires as always;
  · any call of the old turn's brief in that state is counted (`legacy_jev_calls`, a must-be-zero of the proof), so
    another way back is seen at once.

Disarms seen red: the eager door's check removed; the count removed; the counter off the must-be-zero list.
"""
from __future__ import annotations

import sys

import pytest

from nucleo.conversation_host import owed, proof, switch
from voice.engine.pipeline import eager_brief


@pytest.fixture
def fired(monkeypatch):
    from nucleo.turn import brief_turn
    from voice import observer
    got = []
    monkeypatch.setattr(brief_turn, "fire_early", lambda text: got.append(text))
    monkeypatch.setattr(observer, "emit", lambda *a, **k: None)
    yield got
    owed.set_voice_live(False)


def test_the_eager_end_fires_nothing_ever(fired):
    """The manager is the only path (INI-078 F2): the old turn's eager brief is never paid, voice or none."""
    for live in (True, False):
        owed.set_voice_live(live)
        eager_brief.on_preflight("w1 w2")
    owed.set_voice_live(False)
    assert fired == []


def test_an_old_turn_brief_in_that_state_is_counted_and_fails_the_proof(monkeypatch):
    from nucleo.conversation_host import boot
    from nucleo.turn import brief
    monkeypatch.setattr(boot, "account", lambda: "acct-c18")
    monkeypatch.setattr(brief._bt, "prefired", lambda text: None)
    monkeypatch.setattr(brief, "_worker_state", lambda: (False, []))
    monkeypatch.setattr(brief, "_threads", lambda: [])
    monkeypatch.setattr(brief, "ask", lambda text, **kw: {"asked": text})
    try:
        owed.set_voice_live(True)
        brief.ask_for_turn("w1")
        proof.note("acct-c18", "manager_runs")
        got = proof.report("acct-c18")
        assert got["counters"]["legacy_jev_calls"] == 1 and "legacy_jev_calls = 1" in got["fails"]
        owed.set_voice_live(False)
        brief.ask_for_turn("w2")
        assert proof.report("acct-c18")["counters"]["legacy_jev_calls"] == 1
    finally:
        owed.set_voice_live(False)
        proof._by_session.pop("acct-c18", None)
