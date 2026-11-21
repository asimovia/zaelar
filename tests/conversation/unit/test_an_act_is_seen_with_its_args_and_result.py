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


def test_the_send_owner_reads_his_words_in_the_turns_trace(monkeypatch):
    from nucleo.conversation_host import routing, turns
    from nucleo.send import draft, owner
    from voice import trace
    seen = []
    monkeypatch.setattr(turns, "current", lambda: "T_w1")
    monkeypatch.setattr(draft, "current", lambda: object())

    async def take(text, **kw):
        seen.append(trace.current())
        return True, "w_line"
    monkeypatch.setattr(owner, "take", take)
    assert asyncio.run(routing.HostRoute().take("acct", "w_yes")) == "w_line" and seen == ["T_w1"]
