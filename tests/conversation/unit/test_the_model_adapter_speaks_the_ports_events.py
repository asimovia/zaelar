"""The `Model` port over the engine's fast client (node 13.40, v3.1 B3).

The prompt's parts become messages in one order — prefix, conversation, state, input, then the run's steps as a
call and its result. The two orders are tools of their own beside the catalogue and arrive as `Command`s; any
other call is a `ToolCall` with an id of its own; text is `TextDelta`; the end is `Done`. A failure says whose it
is: an HTTP status or a transport error is the provider's, a programming error is ours. Through the manager, an
order the model gives by that call is the run's order, `complete` included.
"""
from __future__ import annotations

import asyncio

from conversation.ports import Command, Done, Failed, PromptParts, TextDelta, ToolCall, ToolResult, ToolSpec, Turn
from conversation.types import Evidence
from nucleo.conversation_host.model import ORDERS, FastModel, messages, tools_for


class _Client:
    def __init__(self, chunks=(), calls=(), raise_=None) -> None:
        self.chunks, self.calls, self.raise_, self.seen = list(chunks), list(calls), raise_, {}

    async def stream(self, msgs, *, spec, tools, on_tool_call, metrics, role, **kw):
        self.seen = {"messages": msgs, "tools": tools, "role": role, "spec": spec}
        metrics.update(model="m0", finish_reason="stop")
        if self.raise_:
            raise self.raise_
        for c in self.chunks:
            yield c
        for name, args in self.calls:
            on_tool_call(name, args)


def _run(model: FastModel, parts: PromptParts, catalog=()) -> list:
    async def go():
        return [ev async for ev in model.stream(parts, list(catalog), run_id="run_1", model_id="")]
    return asyncio.run(go())


P = PromptParts("PREFIX", "STATE", (Turn("user", "voice", "w1"), Turn("agent", "voice", "w2")), "[e1 · voice] w3")


def test_the_parts_become_messages_in_one_order():
    call = ToolCall("run_1:c1", "search", {"q": "w4"})
    res = ToolResult("ok", {"n": 1}, (Evidence("ev1", "search", value=3.0),))
    got = messages(PromptParts(P.prefix, P.state, P.conversation, P.input, ((call, res),)))
    assert [m["role"] for m in got] == ["system", "user", "assistant", "system", "user", "assistant", "tool"]
    assert got[0]["content"] == "PREFIX" and got[3]["content"] == "STATE" and got[4]["content"] == P.input
    assert got[5]["tool_calls"][0]["id"] == "run_1:c1" == got[6]["tool_call_id"]
    assert '"ev1"' in got[6]["content"]


def test_text_orders_and_calls_become_the_ports_events():
    client = _Client(chunks=["w5 ", "w6"], calls=[("search", {"q": "w7"}),
                                                   ("reply", {"text": "w8", "claims": [], "complete": False})])
    got = _run(FastModel(client, spec="spec0"), P, [ToolSpec("search")])
    assert got[:2] == [TextDelta("w5 "), TextDelta("w6")]
    assert isinstance(got[2], Done) and got[2].usage["model"] == "m0"      # the end, before the calls it gathered
    assert isinstance(got[3], ToolCall) and got[3].name == "search" and got[3].call_id.startswith("run_1:")
    assert got[4] == Command("reply", {"text": "w8", "claims": [], "complete": False, "unclaimed_figures": 1})
    names = [t["function"]["name"] for t in client.seen["tools"]]
    assert names == ["search", *ORDERS] and client.seen["role"] == "voice" and client.seen["spec"] == "spec0"


def test_a_failure_says_whose_it_is():
    class Http(Exception):
        status_code = 503
    got = _run(FastModel(_Client(raise_=Http("w9")), spec="s"), P)
    assert got == [Failed("Http: w9", "provider")]
    got = _run(FastModel(_Client(raise_=KeyError("w9")), spec="s"), P)
    assert len(got) == 1 and got[0].whose == "ours"


def test_the_orders_declare_their_fields():
    assert set(ORDERS["reply"]["properties"]) == {"text", "claims", "complete"}
    assert set(ORDERS["no_reply"]["properties"]) == {"reason", "complete", "not_his"}   # not his ≠ nothing to add (R3-A)
    assert all(t["type"] == "function" for t in tools_for([ToolSpec("search", {"type": "object"})]))


def test_through_the_manager_the_models_order_is_the_runs(store):
    from tests.conversation.unit.convkit import Harness
    h = Harness(store, grace=True)
    h.conv.model = FastModel(_Client(calls=[("reply", {"text": "w8", "complete": True})]), spec="s")
    closed = h.utter([(["w1"], 0)], terminal=True)
    h.at(closed + h.conv.cfg.complete_grace_ms + 50).pump()
    assert [o.text for o in h.mouth.orders] == ["w8"]                  # at the short grace its reading earned


class _CutOnce(_Client):
    """The provider cuts the body mid-stream on the first request (`httpx.ReadError` carries no message)."""

    def __init__(self, before=(), **kw) -> None:
        super().__init__(**kw)
        self.before, self.requests = list(before), 0

    async def stream(self, msgs, *, spec, tools, on_tool_call, metrics, role, **kw):
        self.requests += 1
        if self.requests == 1:
            on_tool_call("reply", {"text": "w0", "claims": []})       # half a call gathered before the cut
            for c in self.before:
                yield c
            import httpx
            raise httpx.ReadError("")
        async for c in super().stream(msgs, spec=spec, tools=tools, on_tool_call=on_tool_call, metrics=metrics,
                                      role=role, **kw):
            yield c


def test_a_cut_before_anything_was_yielded_is_resent_whole():
    client = _CutOnce(calls=[("reply", {"text": "w9", "claims": [], "complete": True})])
    got = _run(FastModel(client, spec="spec0"), P)
    assert client.requests == 2
    assert isinstance(got[0], Done) and got[0].usage["resent"] == 1
    assert [g.args["text"] for g in got if isinstance(g, Command)] == ["w9"]   # the first try's half call is gone


def test_a_cut_after_text_was_yielded_is_a_failure_never_a_second_text():
    client = _CutOnce(before=["w5"], calls=[("reply", {"text": "w9", "claims": []})])
    got = _run(FastModel(client, spec="spec0"), P)
    assert client.requests == 1 and got[0] == TextDelta("w5")
    assert isinstance(got[-1], Failed) and got[-1].whose == "provider"


def test_an_error_that_is_not_a_transport_cut_is_not_resent():
    client = _Client(raise_=ValueError("w1"))
    got = _run(FastModel(client, spec="spec0"), P)
    assert len(got) == 1 and isinstance(got[0], Failed)
