"""
A flow says WHO started it, and the pulse's beat is not a flow.

Two contracts the operator reads in both observability surfaces (the engine's ◷ Traces view and the private panel):

1. Every flow carries `initiator` — `user` (his voice, typing or tap) or `system` (kickoff, cron, spark, cluster,
   cluster heartbeat, a rule reacting to a connector event) — declared ONCE by the root event where the flow is born
   (`voice/trace.py::initiator_of`), and projected by `observability.flows.flows()`. Never derived from the text.
2. The pulse is a continuous ~1 Hz process: its beat summaries (`pulse`) and the widgets' clock-driven refreshes
   (`background`) never take the ambient trace. A beat emitted inside a request's context would otherwise join that
   request's flow and stretch it over every beat after it.
"""
from __future__ import annotations

import time

import pytest

from voice import trace

USER = ("turno", "ui", "probe")
SYSTEM = ("kickoff", "cron", "proactivo", "cluster", "pulso", "something-new")


@pytest.mark.parametrize("origin", USER + SYSTEM)
def test_the_root_event_declares_the_initiator_from_its_origin(origin):
    from voice import observer
    tid = trace.begin("x", origin=origin)
    root = [e for e in observer.debug_events(kind="trace") if e.get("trace") == tid][-1]
    want = "user" if origin in USER else "system"
    assert root.get("initiator") == want, f"origin {origin!r} must be born as {want}"
    assert root.get("role") == want
    trace.adopt("")


def test_an_unknown_origin_is_never_counted_as_his():
    assert trace.initiator_of("rule:mail-arrived") == "system"
    assert trace.initiator_of(None) == "system"


@pytest.mark.parametrize("kind", ["pulse", "background"])
def test_a_beat_inside_a_request_does_not_join_its_flow(kind):
    from voice import observer
    tid = trace.begin("play some music", origin="turno")
    assert trace.current() == tid
    ev = observer.emit(kind, "tick", role="system", extra={"n": 1, "ms": 300})
    assert ev is not None and not ev.get("trace"), "a beat never takes the ambient trace"
    work = observer.emit("brain", "decide")
    assert work.get("trace") == tid, "real work in the same context still joins the request"
    trace.adopt("")


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    import bus
    from bus import log as _log

    _log._conn = None
    _log.detach(bus)
    _log.attach(bus)
    from observability import identity as _ident
    _ident._user["id"] = None
    _ident._session["id"] = None
    yield _log
    _log.detach(bus)
    _log._conn = None


def test_flows_project_the_initiator_and_no_beat_opens_a_flow(wired):
    from observability import flows, identity
    from voice.observer import emit

    identity.begin_session("test")
    his = trace.begin("what's the weather in Soria", origin="turno")
    emit("pulse", "beat", role="system", extra={"n": 60, "ticks": 60, "avg_ms": 3, "max_ms": 9, "slow": 0})
    emit("background", "tick", text="clock: 1ms", extra={"id": "clock"})
    emit("brain", "decide")
    heartbeat = trace.begin("[cluster:x · heartbeat] no reply for a while", origin="pulso")
    emit("worker", "start")
    trace.adopt("")
    time.sleep(0.25)

    got = {f["corr_id"]: f for f in flows.flows(limit=10)}
    assert set(got) == {his, heartbeat}, "a beat opens no flow and joins none"
    assert got[his]["events"] == 2, "root + decide; the beats emitted in between are not part of it"
    assert got[his]["initiator"] == "user"
    assert got[heartbeat]["initiator"] == "system"


def test_a_root_written_before_the_flag_falls_back_to_its_declared_origin():
    from observability.flows import _initiator
    assert _initiator({"initiator": None, "origin": "turno"}) == "user"
    assert _initiator({"initiator": None, "origin": "pulso"}) == "system"
    assert _initiator({"initiator": None, "origin": None}) == "system"
    assert _initiator({"initiator": "user", "origin": "cron"}) == "user", "the declared flag wins"
