"""The just-ended errands a request can REOPEN belong to one conversation, and how long each stays reopenable is
declared by how it ended (V2-879 O2).

Measured in the lab sandbox: a search ran, the session was cleaned, and a NEW search for the same kind of thing was
routed `reopen` into the previous run's ENDED errand. The pool `flow_of.candidates` reads (`workers.ended`) was keyed
by the engine's lifetime — and a hard reset even fed it, because the errands it cancels end after it.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from nucleo.turn import flow_of
from nucleo.workers import ended
from nucleo.workers.session import SessionRecord
from observability import identity

GOAL = "Búscame cafeterías de especialidad en Malasaña"


@pytest.fixture
def session(monkeypatch):
    """One conversation, then another: what `rotate_session` does to the identity, without its side effects."""
    monkeypatch.setitem(identity._session, "id", "s-1")
    monkeypatch.setitem(identity._session, "started_ms", round((time.time() - 60) * 1000))
    monkeypatch.setattr(ended, "_POOL", {"sid": "", "since": 0.0})
    monkeypatch.setattr("nucleo.dispatch.pending_summaries", lambda: [])

    def new_session():
        identity._session["id"] = f"s-{int(identity._session['id'][2:]) + 1}"
        identity._session["started_ms"] = round(time.time() * 1000)
    return new_session


def _ended(tid: str, *, status: str = "done", ok: bool = True, started: float | None = None) -> SessionRecord:
    rec = SessionRecord(task_id=tid, goal=GOAL, status=status, ok=ok)
    if started is not None:
        rec.started = started
    ended._remember_ended(rec)
    return rec


def _ended_flows() -> list[str]:
    return [str(c["id"]) for c in flow_of.candidates() if c.get("ended") or c.get("delivered")]


def test_a_new_session_leaves_nothing_to_reopen(session):
    _ended("1")
    assert _ended_flows() == ["1"], "the just-ended errand is not even a flow in its own session"
    session()
    assert _ended_flows() == [], "a cleaned session kept the previous conversation's errand reopenable"


def test_an_errand_cancelled_by_the_clean_does_not_land_in_the_new_session(session):
    born = time.time() - 30                     # started in the conversation the clean ends…
    assert _ended_flows() == []                 # (every turn of that conversation read the pool: its route did)
    session()
    _ended("2", status="cancelled", ok=False, started=born)    # …and its end lands after the clean
    assert _ended_flows() == []


def test_the_route_of_the_same_request_after_a_clean_is_new(session, monkeypatch):
    async def judge(text, pool):                # the judge folds the same kind of thing into the ended errand
        return next((str(c["id"]) for c in pool if c.get("ended")), ""), False
    monkeypatch.setattr("nucleo.turn.flow_judge.judge", judge)
    _ended("3")
    assert asyncio.run(flow_of.route(GOAL))["as"] == flow_of.REOPEN
    session()
    assert asyncio.run(flow_of.route(GOAL))["as"] == flow_of.NEW


@pytest.mark.parametrize("status, ok, kind", [("done", True, "delivered"), ("done", False, "done"),
                                              ("error", False, "error"), ("cancelled", False, "cancelled"),
                                              ("running", False, "error")])
def test_how_long_an_end_stays_reopenable_is_declared_by_how_it_ended(session, status, ok, kind):
    _ended("4", status=status, ok=ok)
    assert ended.end_of(ended._ENDED_SESSIONS["4"]) == kind and kind in ended.REOPEN_GRACE_S
    ended._ENDED_SESSIONS["4"]["at"] = time.time() - ended.REOPEN_GRACE_S[kind] + 5
    assert _ended_flows() == ["4"]
    ended._ENDED_SESSIONS["4"]["at"] = time.time() - ended.REOPEN_GRACE_S[kind] - 5
    assert _ended_flows() == [], f"a {kind} end past its declared grace is still reopenable"
