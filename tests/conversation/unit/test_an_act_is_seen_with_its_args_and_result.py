"""An act is seen with its arguments and what it answered, in its order's flow (node 13.148, C6).

A read's event carried its arguments; an act's did not, nor what its door answered — an audit of his session could not
tell what was done. Now the act's `claimed` carries its arguments, bounded, and its `receipt` the door's status and
answer, bounded. And the send owner reads his words in the trace of the turn in course, so what it emits is the order's
flow.
"""
from __future__ import annotations

import asyncio

from conversation.ports import Done, ToolCall, ToolResult
from conversation.testing.scripted_model import reply
from tests.conversation.unit.convkit import Harness


def test_an_acts_events_carry_its_args_and_what_its_door_answered(store):
    h = Harness(store, grace=False)
    h.tools.answers["agenda_add"] = ToolResult("ok", data={"id": 7, "title": "w_dentist"}, receipt={"delivered": True})
    h.model.default = lambda ids: ([ToolCall("c1", "agenda_add", {"title": "w_dentist"}), Done()]
                                   if len(h.model.calls) == 1 else [reply("w9"), Done()])
    h.typed("w1", 0)
    h.settle(3000)
    effects = [(lab, p) for k, lab, p in h.tel.events if k == "conv_effect"]
    claimed = next(p for lab, p in effects if lab == "claimed")
    got = next(p for lab, p in effects if lab == "receipt")
    assert claimed["args"] == {"title": "w_dentist"}
    assert got["status"] == "ok" and '"title": "w_dentist"' in got["result"]


def test_on_a_real_engine_loop_in_another_thread_the_order_runs_in_its_trace(monkeypatch):
    """The engine's loop is another thread: what the order runs there carries the trace of the turn that ordered it,
    from the host's act door (`HostTools.call` puts it in the turn's trace) to the coroutine on that loop."""
    import threading

    from nucleo import dispatch
    from nucleo.conversation_host import acts, acts_widget, turns
    from voice import trace
    loop = asyncio.new_event_loop()
    engine = threading.Thread(target=loop.run_forever, daemon=True)
    engine.start()
    seen = []

    async def on_the_engine():
        seen.append((trace.current(), threading.current_thread() is engine))
        return {"ok": True}
    try:
        monkeypatch.setattr(dispatch, "_LOOP", loop)
        monkeypatch.setattr(turns, "current", lambda: "T_w1")
        monkeypatch.setattr(acts.HostTools, "_call", lambda *a, **k: acts_widget._on_engine_loop(on_the_engine()))
        asyncio.run(acts.HostTools().call("widget_action", {}, effect_id="e1", idempotency_key="k1",
                                          deadline_mono_ms=0))
    finally:
        loop.call_soon_threadsafe(loop.stop)
        engine.join(2)
    assert seen == [("T_w1", True)]


def test_an_events_run_gives_its_acts_its_own_trace(monkeypatch):
    """An event's run (a message, a cron) has a trace of its own: its acts run in it, never in none."""
    from nucleo.conversation_host import turns
    from voice import trace
    monkeypatch.setattr(trace, "begin", lambda *a, **k: "T_ev1")
    monkeypatch.setitem(turns._in_course, "run", "")
    turns.listen("conv_run", "started", {"refs": {"run": "run_ev1"}, "origin": "w_message"})
    try:
        assert turns.current() == "T_ev1"
    finally:
        turns.listen("conv_run", "ended", {"refs": {"run": "run_ev1"}})
    assert turns.current() == ""
