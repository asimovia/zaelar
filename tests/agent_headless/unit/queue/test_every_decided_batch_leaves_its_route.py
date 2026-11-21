"""Every batch the one decider decides leaves ONE `route` record, with what it saw and what it chose (INI-078 S1).

The conversation's own telemetry (a run starts, its words come in, its model answers, it ends) and the host's ports
(the state block it read, each act with its arguments, our last line) make one `route` event in the turn's flow; its
class is derived from the acts by the declared table. The auditor's reader gives it back by session. Nothing synthetic
is judged here: this pins the RECORD, the mark is the auditor's on his real sessions.
"""
from __future__ import annotations

import json

import pytest

from nucleo.conversation_host import route, turns


@pytest.fixture
def emitted(monkeypatch):
    from voice import observer
    out = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None, **kw:
                        out.append((kind, label, dict(extra or {}))) if kind == "route" else None)
    monkeypatch.setitem(turns._in_course, "run", "run-1")
    route._runs.clear()
    return out


def _batch(*acts, words=("w1 w2",)):
    route.listen("conv_run", "started", {"refs": {"run": "run-1"}, "batch_envs": ["e1"]})
    route.listen("conv_run", "input", {"refs": {"run": "run-1"}, "text": list(words)})
    route.saw("TASKS", "running: [t1] w3")
    for name, args in acts:
        route.acted(name, args, "ok")
    route.listen("conv_run", "model_done", {"refs": {"run": "run-1"}, "model": "w-model"})
    route.listen("conv_run", "ended", {"refs": {"run": "run-1"}, "outcome": "answered"})


def test_a_decided_batch_leaves_one_route_with_everything_it_saw_and_chose(emitted):
    route.ours("w0 earlier")
    _batch(("start_task", {"request": "w4"}), ("start_task", {"request": "w5"}))
    (kind, label, e), = emitted
    assert label == "route/B" and e["class"] == "B"
    assert e["his_text"] == "w1 w2" and e["our_last"] == "w0 earlier" and e["open"] == "running: [t1] w3"
    assert [a["args"]["request"] for a in e["acts"]] == ["w4", "w5"] and e["model"] == "w-model"
    assert e["batch_ids"] == ["e1"] and e["outcome"] == "answered" and e["ms"] >= 0


@pytest.mark.parametrize("acts,cls", [((), "A"), ((("widget_action", {}),), "A"), ((("task_answer", {}),), "C"),
                                      ((("stop_task", {}), ("start_task", {})), "D")])
def test_the_class_comes_from_the_declared_table(emitted, acts, cls):
    _batch(*acts)
    assert emitted[0][2]["class"] == cls


def test_an_events_run_decides_nothing_of_his(emitted):
    route.listen("conv_run", "started", {"refs": {"run": "run-9"}, "origin": "email"})
    route.listen("conv_run", "ended", {"refs": {"run": "run-9"}, "origin": "email"})
    assert emitted == []


def test_the_auditor_reads_it_back_by_session(monkeypatch):
    from nucleo.audit import route as audit
    from observability import flows
    rows = [{"kind": "route", "label": "route/C", "ts_ms": 1, "corr_id": "T1",
             "payload": json.dumps({"extra": {"class": "C", "his_text": "w1", "acts": [{"name": "task_answer"}]}})},
            {"kind": "brain", "label": "x", "payload": "{}"},
            {"kind": "route", "label": "near", "payload": json.dumps({"extra": {"new": "7", "open": "3"}})}]
    monkeypatch.setattr(flows, "events", lambda session_id="", limit=0, **kw: rows)
    got = audit.decisions("s-1")
    assert [d.get("class") for d in got] == ["C", None] and got[1]["near"] == {"new": "7", "open": "3"}
