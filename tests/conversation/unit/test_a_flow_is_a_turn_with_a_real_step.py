"""A flow is a turn with a real step, and it is the conversation's (node 13.141, E7d-5, R-1).

A turn's `flow end` carries the conversation's family (never the `flow` kind's default, `worker`), the real steps its
run made (its reads and acts, and its answer — never the run's own repair steps) and the tasks it opened (the declared
`task_acts`). The acts of a run run in its turn's trace, so what they start is the order's flow. An event's run opens a
trace of its own with its origin; it is a flow only when it did something — one with nothing to do is counted apart.
"""
from __future__ import annotations

import asyncio

import pytest

from conversation.ports import ToolCall, ToolResult
from nucleo.conversation_host import turns


@pytest.fixture
def seen(monkeypatch):
    from voice import observer
    out = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None, **k: out.append(
        (kind, label, dict(extra or {}), __import__("voice.trace", fromlist=["x"]).current())))
    turns._reset_for_tests()
    yield out
    turns._reset_for_tests()


def _turn(run: str) -> str:
    turns.listen("conv_inbox", "accepted", {"kind": "user.text", "text": "w_find me a flat", "refs": {"iv": "i1",
                                                                                                    "env": "e1"}})
    turns.listen("conv_run", "started", {"refs": {"run": run}, "batch_envs": ["e1"]})
    return turns.known("i1")


def test_a_turns_flow_end_is_the_conversations_with_its_real_steps_and_tasks(seen):
    tid = _turn("run1")
    assert turns.current() == tid
    turns.listen("conv_effect", "read", {"refs": {"run": "run1"}, "tool": "web_search"})
    turns.listen("conv_effect", "submitted", {"refs": {"run": "run1"}, "tool": "start_task"})
    turns.listen("conv_close", "answered", {"refs": {"req": "r_i1", "run": "run1"}})
    turns.listen("conv_run", "ended", {"refs": {"run": "run1"}, "outcome": "answered"})
    end = [(x, t) for k, lab, x, t in seen if (k, lab) == ("flow", "end")]
    assert end == [({"ok": True, "reason": "turn_complete", "closed": "answered", "cat": "conversation", "steps": 3,
                     "tasks": 1}, tid)]
    assert turns.current() == ""


def test_an_event_opens_its_own_trace_and_is_a_flow_only_when_it_did_something(seen):
    turns.listen("conv_run", "started", {"refs": {"run": "ev1"}, "origin": "connector.msg"})
    turns.listen("conv_run", "ended", {"refs": {"run": "ev1"}, "outcome": "answered", "origin": "connector.msg"})
    turns.listen("conv_run", "started", {"refs": {"run": "ev2"}, "origin": "cron.due"})
    turns.listen("conv_run", "ended", {"refs": {"run": "ev2"}, "outcome": "silent", "reason": "nothing",
                                       "origin": "cron.due"})
    roots = [lab for k, lab, x, t in seen if k == "trace"]
    ends = [x for k, lab, x, t in seen if (k, lab) == ("flow", "end")]
    assert len(roots) == 2 and turns.current() == ""
    assert [(e["origin"], e["steps"], e.get("discarded")) for e in ends] == [("connector.msg", 1, None),
                                                                             ("cron.due", 0, "nothing")]
    assert all(e["cat"] == "conversation" for e in ends)


def test_an_act_runs_in_its_turns_trace(seen, monkeypatch):
    from nucleo.conversation_host import acts
    from voice import trace
    tid = _turn("run2")
    traced = []

    async def door(name, args, **kw):
        traced.append(trace.current())
        return ToolResult("ok", {})
    tools = acts.HostTools()
    monkeypatch.setattr(tools, "_call", door)
    asyncio.run(tools.call("show_widget", {}, effect_id="x", idempotency_key="x", deadline_mono_ms=0))
    assert traced == [tid]


def test_a_close_counts_the_runs_real_steps_never_its_repairs():
    from conversation.manager import run
    steps = [(ToolCall("c1", "web_search", {}), ToolResult("ok")), (ToolCall(run.ORDERS_ID, "orders_check", {}),
             ToolResult("refused")), (ToolCall(run.READS_ID, "reads_check", {}), ToolResult("refused"))]
    assert run._real(steps) == 1
