"""The worker's brief carries a short block of the state now, and ONE bridge act reads it again fresh.

Measured: a worker started blind to which channels were connected, which widgets were open, which tasks were in
flight and which MeshKore clusters it belonged to, and spent model turns rediscovering them. Now the handoff carries
those four facts as names (each from its owner, an unreadable one left out) and `act state` returns the same
snapshot. Variants: every fact present, none present, es and en.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.workers import state_now
from nucleo.workers.prompts import first_act


@pytest.fixture(params=["es", "en"])
def lang(request, monkeypatch):
    from i18n import langs
    monkeypatch.setattr(langs, "current_code", lambda: request.param)
    monkeypatch.setattr(langs, "current_language", lambda: langs.LANGUAGES[request.param])
    return request.param


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setattr(state_now, "channels", lambda: {"telegram": "connected", "whatsapp": "off"})
    monkeypatch.setattr(state_now, "widgets", lambda: ["agenda", "contactos"])
    monkeypatch.setattr(state_now, "tasks", lambda own="": [
        {"id": str(i), "title": "t" * 50, "state": "running"} for i in range(9)])
    monkeypatch.setattr(state_now, "clusters", lambda: [{"name": "vecinos", "connected": True}])


def test_the_handoff_names_the_four_facts_short(lang, world):
    out = first_act.block("row-1", {}, {})
    for name in ("telegram (connected)", "whatsapp (off)", "agenda, contactos", "vecinos (connected)", "+6"):
        assert name in out, name
    assert "act state" in out, "the block names the call that refreshes it"
    assert len(state_now.block("row-1")) < 600, "names only: the brief stays under its ceiling"


def test_nothing_known_is_no_block(lang, monkeypatch):
    for f in ("channels", "widgets", "clusters"):
        monkeypatch.setattr(state_now, f, lambda: {} if f == "channels" else [])
    monkeypatch.setattr(state_now, "tasks", lambda own="": [])
    assert state_now.block("x") == ""


def test_the_state_act_returns_the_snapshot_fresh(world, monkeypatch):
    from nucleo.cli import worker_api
    from nucleo.workers.session import SessionRecord
    assert worker_api.classify_act("state", {}) == worker_api.ALLOW
    rec = SessionRecord(task_id="1", goal="x")
    got = asyncio.run(worker_api._exec_allow("state", {}, rec))
    assert got["ok"] and set(got["result"]) == {"channels", "widgets", "tasks", "clusters"}
    assert got["result"]["widgets"] == ["agenda", "contactos"]


def test_this_task_is_not_among_his_other_tasks(monkeypatch):
    class _Store:
        def tasks_where(self, **k):
            return [{"id": "me", "title": "mine", "state": "running"},
                    {"id": "b", "title": "other", "state": "waiting", "waiting_for": "user_answer"}]
    from nucleo.circuit import ledger
    monkeypatch.setattr(ledger, "store", lambda: _Store())
    assert state_now.tasks("me") == [{"id": "b", "title": "other", "state": "waiting_him"}]


def test_disarmed_a_handoff_without_the_state_names_none_of_it(lang, world, monkeypatch):
    """RED proof: with the state reader disarmed the worker starts blind again."""
    monkeypatch.setattr(state_now, "block", lambda own="": "")
    assert "vecinos" not in first_act.block("row-1", {}, {})
