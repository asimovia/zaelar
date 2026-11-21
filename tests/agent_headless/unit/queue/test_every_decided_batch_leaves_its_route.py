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


@pytest.mark.parametrize("acts,cls", [((), "A"), ((("widget_action", {}),), "A"), ((("task_say", {}),), "C"),
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


def test_the_record_holds_the_draft_an_act_the_gateway_refused_and_why_a_door_failed(emitted):
    route.listen("conv_run", "started", {"refs": {"run": "run-1"}, "batch_envs": ["e1"]})
    route.saw("OPEN", "#3 · send · waiting · w3")
    route.saw("DRAFT", "#3: a message being written")
    route.acted("task_say", {"task": "#9"}, "failed", {"reason": "not_open", "open": "#3 …"})
    route.listen("conv_effect", "refused", {"refs": {"run": "run-1"}, "tool": "start_task", "reason": "held"})
    route.listen("conv_effect", "refused", {"refs": {"run": "run-other"}, "tool": "w_x", "reason": "held"})
    route.listen("conv_run", "ended", {"refs": {"run": "run-1"}, "outcome": "answered"})
    (_kind, _label, e), = emitted
    assert e["open"] == "#3 · send · waiting · w3\nDRAFT: #3: a message being written"
    assert [(a["name"], a["status"]) for a in e["acts"]] == [("task_say", "failed:not_open"),
                                                              ("start_task", "refused:held")]
    assert e["class"] == "C"


def test_the_auditors_reader_gives_each_decision_the_signals_that_followed_it():
    from nucleo.audit import route as audit
    act = lambda name, status="ok", **args: {"name": name, "args": args, "status": status}   # noqa: E731
    rows = [{"ts_ms": 0, "class": "B", "acts": [act("start_task", request="w1")]},
            {"ts_ms": 10_000, "class": "C", "acts": [act("task_say", task="#4"), act("draft_edit", task="#5")]},
            {"ts_ms": 30_000, "class": "D", "acts": [act("stop_task", task="#7")]},        # not the #4 undone
            {"ts_ms": 70_000, "class": "C", "acts": [act("task_unsay", task="#4"), act("draft_edit", task="#5")]},
            {"ts_ms": 400_000, "class": "C", "acts": [act("task_say", "failed:not_open", task="#9"),
                                                      act("start_task", "refused:held")]}]
    got = [d["hints"] for d in audit.hints(rows)]
    assert got[0] == ["stopped_soon"]
    assert got[1] == ["undone:task_unsay", "redrafted"]
    assert got[2] == [] and got[3] == []
    assert got[4] == ["not_open:task_say", "refused:start_task"]
