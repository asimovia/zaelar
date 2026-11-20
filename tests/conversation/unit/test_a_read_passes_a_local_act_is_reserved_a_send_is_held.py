"""A read passes, a local act is reserved and sent once, a send is held — and a control nobody here handles is refused
when accepted (node 13.32, INI-078 F2 step 1).

The gateway has three branches, by the class the host derived from the tool's declared act (`ToolSpec.effect_class`;
the package holds no list of tools, and the act itself is opaque to it): a read passes; a local act (a write here) is
RESERVED — every intervention of the person's in the batch sealed and ONE row per operation, in one transaction — and
reaches the `Tools` port only through `dispatch.submit`, with its effect id; the same operation again is the same row
and is never sent twice; something that leaves is refused (`held`) and reaches neither the port nor the ledger; and
while the person speaks every act is refused with that reason. A model whose act did not land answers with it. The
model's `on` never reaches the port.

The controls by id: a stop is always handled; cancelling a task is handled only when the host gives the `Tasks` port;
any other (the confirmation and the delegation of F2) has no handler and is accounted `refused` in the transaction that
accepts it — never left for the sweep's bound. A stop never cancels a task (D3).
"""
from __future__ import annotations

import asyncio

from conversation.gateway import dispatch
from conversation.gateway.outbox import Claimed, Read, Refused
from conversation.inbox.accounting import audit, outcomes
from conversation.ports import Done, ToolCall, ToolSpec
from conversation.testing.fakes import FakeTasks
from conversation.testing.scripted_model import reply
from conversation.types import ControlOp, EffectClass
from tests.conversation.unit.convkit import Harness
from tests.conversation.unit.gatekit import ACCT, Kit, RecordingTools
from tests.conversation.unit.inboxkit import control


def test_a_read_passes_a_local_act_is_reserved_and_a_send_is_held_with_its_event(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    ctx = k.ctx(k.utterance("iv1"))
    assert k.gw.request(ctx, ToolCall("c", "search", {"q": "w1"})) == Read()
    assert k.gw.request(ctx, k.send()) == Refused("held")
    assert k.gw.request(ctx, ToolCall("c", "w_unknown", {})) == Refused("unknown_tool")
    assert k.gw.request(ctx, ToolCall("c", "agenda_add", {"what": "w1"}), held=True) == Refused("person_speaking")
    assert not k.items("effect")                                   # nothing refused ever reaches the ledger
    first = k.gw.request(ctx, ToolCall("c", "agenda_add", {"what": "w1"}))
    again = k.gw.request(ctx, ToolCall("c2", "agenda_add", {"what": "w1"}))
    assert isinstance(first, Claimed) and not first.repeat
    assert again == Claimed(first.effect_id, repeat=True)          # the same operation: the same row, never a second
    assert [r["id"] for r in k.items("effect")] == [first.effect_id]
    assert store.snapshot(ACCT).get("interventions", "iv1")["phase"] == "sealed"
    refused = [p for _k, lab, p in telemetry.events if lab == "refused"]
    assert [(p["tool"], p["act"], p["effect_class"], p["reason"]) for p in refused] == [
        ("send_message", "a2.send", "leaves", "held"), ("w_unknown", None, None, "unknown_tool"),
        ("agenda_add", "a1.add", "write", "person_speaking")]


def test_the_class_is_the_hosts_derivation_never_a_list_of_the_package(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    ctx = k.ctx(k.utterance("iv1"))
    for cls, expected in ((EffectClass.READ, Read), (EffectClass.WRITE, Claimed), (EffectClass.LEAVES, Refused)):
        k.gw.specs = lambda cls=cls: {"w_tool": ToolSpec("w_tool", act="a9.x", effect_class=cls)}
        assert isinstance(k.gw.request(ctx, ToolCall("c", "w_tool", {"n": str(cls)})), expected), cls


def test_a_local_act_reaches_the_tools_once_by_its_reservation_and_a_send_never(store):
    h = Harness(store, grace=False)
    h.model.script["iv_000001"] = [
        [ToolCall("c1", "agenda_add", {"what": "w1"}), ToolCall("c2", "send_message", {"to": "c1", "text": "w2"}),
         ToolCall("c3", "agenda_add", {"what": "w1"}), ToolCall("c4", "search", {"q": "w3", "on": "iv_000001"}),
         Done()],
        [reply("w9"), Done()]]
    h.utter([(["w1", "w2"], 0)])
    [eff] = [r for _k, r in store.snapshot("acct-test").scan("items") if r["kind"] == "effect"]
    assert [(n, a, e) for n, a, e in h.tools.calls] == [("agenda_add", {"what": "w1"}, eff["id"]),
                                                         ("search", {"q": "w3"}, None)]   # `on` never reaches it
    assert eff["state"] == "provider_accepted"
    results = [(c.name, r.status, r.data.get("reason"), r.data.get("repeat")) for c, r in h.model.calls[-1].prompt.steps]
    assert results == [("agenda_add", "ok", None, None), ("send_message", "refused", "held", None),
                       ("agenda_add", "ok", None, True), ("search", "ok", None, None)]
    assert [o.text for o in h.mouth.orders] == ["w9"] and [lab for lab, _ in h.closes()] == ["answered"]


def test_dispatch_reads_only_a_read(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    tools = RecordingTools()
    refused = asyncio.run(dispatch.read(k.gw, tools, ToolCall("c", "agenda_add", {"what": "w1"}), 10 ** 9))
    assert refused.status == "refused" and refused.data["reason"] == "not_a_read" and not tools.calls


def test_a_control_nobody_handles_is_refused_when_accepted(store):
    h = Harness(store)
    for i, op in enumerate((ControlOp.CONFIRM, ControlOp.DECLINE, ControlOp.DELEGATE, ControlOp.CANCEL_TASK)):
        h.conv.give(control(op, 0, f"k{i}", endpoint="d1", gesture=True, handle="h1", task="t1"))
    snap = store.snapshot("acct-test")
    assert sorted(outcomes(snap).values()) == ["refused"] * 4
    assert all(r["accounted_ms"] == r["accepted"] and r["reason"] == "no_handler" for _k, r in snap.scan("inbox"))
    assert audit(snap, h.clock.now_ms(), h.conv.cfg, drained=True) == []            # nothing waits for the sweep
    accounted = [p for k, lab, p in h.tel.events if k == "conv_inbox" and lab == "accounted"]
    assert [(p["outcome"], p["reason"]) for p in accounted] == [("refused", "no_handler")] * 4


def test_with_the_tasks_port_a_button_cancels_its_task_and_a_stop_never_does(store):
    tasks = FakeTasks()
    h = Harness(store, tasks=tasks)
    h.conv.give(control(ControlOp.STOP, 0, "k1", endpoint="d1"))
    h.conv.give(control(ControlOp.CANCEL_TASK, 0, "k2", endpoint="d1", gesture=True, task="t7"))
    assert tasks.cancelled == ["t7"]
    assert sorted(outcomes(store.snapshot("acct-test")).values()) == ["applied", "applied"]


def test_a_tool_with_no_declared_class_never_reaches_the_tools(store):
    """Review TA-3: the one door out is never open by default — a tool whose class the host did not derive (an act
    and no class) is refused as undeclared, and neither the gateway nor `dispatch.read` lets it through."""
    h = Harness(store)
    h.tools.specs = [*h.tools.specs, ToolSpec("w_send", act="a2.send")]
    h.model.script["iv_000001"] = [[ToolCall("c1", "w_send", {"to": "c1"}), Done()], [reply("w9"), Done()]]
    h.utter([(["w1"], 0)])
    assert not h.tools.calls
    result = h.model.calls[-1].prompt.steps[-1][1]
    assert result.status == "refused" and result.data["reason"] == "undeclared"
    k = Kit(store, h.clock, h.tel, owner="k2")
    k.gw.specs = lambda: {"w_send": ToolSpec("w_send", act="a2.send")}
    out = asyncio.run(dispatch.read(k.gw, RecordingTools(), ToolCall("c", "w_send", {}), 10 ** 9))
    assert out.status == "refused"
