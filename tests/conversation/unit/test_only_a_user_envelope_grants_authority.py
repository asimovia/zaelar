"""I8/A3: only the person's entries grant authority, judged per effect from the run's batch (node 13.13, plan §15).

A read passes from any batch. An effect rests on a batch that is ALL the person's (the authority floor); a batch caused by a
contact or a worker — or one that mixes the person's sentence with theirs — lends nothing: the effect needs a gesture
(`NeedsConfirmation`) or a mandate, and a mandate never serves a batch that carries no content of the person (M4). The model's `on` changes nothing. `destructive` and `payment` always need a
gesture; a delegation covers `egress` only, and only a gesture creates one; a grant is created only from an all-user
batch under a covering delegation and matches its exact operation. A refused or held proposal does NOT cut the
writes (E5); a call that reaches dispatch without a reservation does.
"""
from __future__ import annotations

import asyncio

from conversation.gateway.outbox import Claimed, NeedsConfirmation, Read, Refused
from conversation.gateway import dispatch
from conversation.ports import ToolCall
from conversation.types import Channel, ControlOp
from tests.conversation.unit.gatekit import Kit, RecordingTools

ADD = ToolCall("c", "agenda_add", {"what": "w0001"})
SCOPE = {"recipients": ["c1"], "channel": "chat", "expires_ms": 10 ** 15, "max": 2}


def test_destructive_and_payment_always_need_a_gesture(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    k.gw.delegate(k.control(ControlOp.DELEGATE, scope=SCOPE))
    voice = k.utterance("iv1")
    assert isinstance(k.gw.request(k.ctx(voice), ToolCall("c", "delete_all", {})), NeedsConfirmation)
    assert isinstance(k.gw.request(k.ctx(voice), ToolCall("c", "pay", {"to": "c1", "amount": 1})), NeedsConfirmation)


def test_a_delegation_exists_only_by_a_gesture_and_covers_egress_up_to_its_maximum(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    assert k.gw.delegate(k.control(ControlOp.DELEGATE, scope=SCOPE, gesture=False, channel=Channel.TEXT)) \
        == Refused("not_a_gesture")
    assert isinstance(k.gw.request(k.ctx(k.utterance("iv0")), k.send()), NeedsConfirmation)
    k.gw.delegate(k.control(ControlOp.DELEGATE, scope=SCOPE))
    got = [k.gw.request(k.ctx(k.utterance(f"iv{i}")), k.send(text=f"w{i}")) for i in (1, 2, 3)]
    assert [type(g).__name__ for g in got] == ["Claimed", "Claimed", "NeedsConfirmation"]
    assert isinstance(k.gw.request(k.ctx(k.utterance("iv9")), k.send(to="c2")), NeedsConfirmation)


def test_a_call_that_reaches_dispatch_without_a_reservation_cuts_the_writes(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    tools = RecordingTools()
    assert asyncio.run(dispatch.submit(k.gw, tools, "x_never_reserved", 10 ** 9)) is None
    assert k.flags().get("on") and not tools.calls
    assert k.gw.request(k.ctx(k.utterance("iv1")), ADD) == Refused("write_disabled")
    assert k.gw.request(k.ctx(k.utterance("iv2")), ToolCall("c", "search", {})) == Read()   # reads go on


def test_minor3_a_read_goes_without_the_models_hint_and_an_act_never_passes_as_a_read(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    tools = RecordingTools()
    out = asyncio.run(dispatch.read(k.gw, tools, ToolCall("c", "search", {"q": "w1", "on": "iv9"}), 10 ** 9))
    assert out.status == "ok" and tools.calls[-1][1] == {"q": "w1"}       # `on` never reaches the port
    refused = asyncio.run(dispatch.read(k.gw, tools, ToolCall("c", "agenda_add", {"what": "w1"}), 10 ** 9))
    assert refused.status == "refused" and refused.data["reason"] == "not_a_read" and len(tools.calls) == 1


def test_minor11_a_repeat_of_a_withdrawn_effect_says_so_and_finds_it_by_its_index(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    voice = k.utterance("iv1")
    first = k.gw.request(k.ctx(voice), ADD)
    assert isinstance(first, Claimed)
    with k.gw.book.tx() as b:
        b.move(first.effect_id, "withdrawn")
    again = k.gw.request(k.ctx(voice), ADD)
    assert again == Refused("repeat_of_withdrawn")
    assert store.snapshot("acct-test").scan("effect_ops")               # the index the repeat is read from
