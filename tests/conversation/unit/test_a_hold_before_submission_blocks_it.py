"""A7: a hold received before an effect is submitted blocks it; after submission it changes nothing (node 13.15).

A hold from ANY of the person's devices, received after the effect was claimed and before it was submitted, keeps it from
going — and keeps it there however much time passes: a hold is never released by a clock. Another device cannot
release it, nor a non-gesture; a gesture on the device that initiated the effect commits it. A hold older than the
claim, or one that arrives once the effect is submitting, changes nothing.
"""
from __future__ import annotations

import asyncio

from conversation.gateway import dispatch
from conversation.ports import ToolCall
from tests.conversation.unit.gatekit import ACCT, Kit, RecordingTools

ADD = ToolCall("c", "agenda_add", {"what": "w0001"})


def _claim(k: Kit) -> str:
    return k.gw.request(k.ctx(k.utterance("iv1"), endpoint="d1"), ADD).effect_id


def _state(store, eid):
    return store.snapshot(ACCT).get("items", eid)["state"]


def test_a_hold_after_the_claim_blocks_until_the_initiating_device_commits_by_gesture(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    clock.advance(1000)
    eid = _claim(k)
    dispatch.hold(k.gw, "hd1", "d2", clock.now_ms() + 10, "onset")
    tools = RecordingTools()
    assert asyncio.run(dispatch.submit(k.gw, tools, eid, 10 ** 9)) is None
    clock.advance(3_600_000)                                                   # an hour: never released by time
    assert asyncio.run(dispatch.submit(k.gw, tools, eid, 10 ** 9)) is None
    assert not dispatch.release(k.gw, eid, "d2", gesture=True)                 # not the device that initiated it
    assert not dispatch.release(k.gw, eid, "d1", gesture=False)                # not a gesture
    assert not tools.calls and _state(store, eid) == "claimed"
    assert dispatch.release(k.gw, eid, "d1", gesture=True)
    assert asyncio.run(dispatch.submit(k.gw, tools, eid, 10 ** 9)).status == "ok"
    assert len(tools.calls) == 1 and _state(store, eid) == "delivered"
    assert "conv_effect/held" in telemetry.labels() and "conv_effect/released" in telemetry.labels()


def test_a_hold_older_than_the_claim_does_not_block(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    dispatch.hold(k.gw, "hd0", "d2", clock.now_ms(), "onset")
    clock.advance(500)
    eid = _claim(k)
    assert asyncio.run(dispatch.submit(k.gw, RecordingTools(), eid, 10 ** 9)).status == "ok"


def test_a_hold_after_submission_changes_nothing(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    eid = _claim(k)
    tools = RecordingTools()

    class HoldDuringCall(RecordingTools):
        async def call(self, name, args, **kw):
            dispatch.hold(k.gw, "hd2", "d2", clock.now_ms() + 1, "onset")      # arrives while it is going
            return await tools.call(name, args, **kw)

    assert asyncio.run(dispatch.submit(k.gw, HoldDuringCall(), eid, 10 ** 9)).status == "ok"
    assert _state(store, eid) == "delivered" and len(tools.calls) == 1


def test_m8_the_person_speaking_on_another_device_holds_an_action_unclaimed_and_unsealed(store):
    """From the manager, not the primitive (audit M8): while a run is on, an onset on another device makes the next
    action Held — nothing claimed, the revision not sealed — so what they go on saying is not an amendment."""
    from conversation.ear import signals as S
    from conversation.gateway import seal as SEAL
    from conversation.ports import Done
    from conversation.testing.scripted_model import reply
    from tests.conversation.unit.convkit import Harness

    h = Harness(store)
    h.model.script["iv_000001"] = [[lambda: h.hear(S.VadEdge("d2", "rise", h.clock.mono + 5)),
                                    ToolCall("c", "agenda_add", {"what": "w1"}), Done()], [reply("w2"), Done()]]
    h.utter([(["w1"], 0)])
    assert not [r for _k, r in store.snapshot("acct-test").scan("items") if r["kind"] == "effect"]
    assert h.tools.calls == []
    held = [p for k, lab, p in h.tel.events if k == "conv_effect" and lab == "held"]
    assert held and held[0]["reason"] == "person_speaking"


def test_m8_a_hold_after_a_confirmation_blocks_its_send_until_the_initiating_device_commits(store):
    from conversation.ear import signals as S
    from conversation.ports import Done
    from conversation.testing.scripted_model import reply
    from conversation.types import ControlOp
    from tests.conversation.unit.convkit import Harness
    from tests.conversation.unit.inboxkit import control
    h = Harness(store, script={"iv_000001": [[ToolCall("c", "send_message", {"to": "c1", "via": "chat",
                                                                               "text": "w5"}), Done()],
                                             [reply("w6?"), Done()]]})
    h.utter([(["w1"], 0)])
    handle = [r for _k, r in store.snapshot("acct-test").scan("items") if r["kind"] == "handle"][0]
    h.live = False
    h.conv.give(control(ControlOp.CONFIRM, 0, "k1", endpoint="d1", gesture=True, handle=handle["id"]))
    h.at(h.clock.mono + 10)
    from conversation.gateway import dispatch
    dispatch.hold(h.conv.gw, "hold-x", "d2", h.clock.now_ms(), "onset")   # «wait» on the phone
    h.pump()
    assert h.tools.calls == []
    effect = [r for _k, r in store.snapshot("acct-test").scan("items") if r["kind"] == "effect"][0]
    assert not h.conv.release(effect["id"], "d2", gesture=True)            # not the device that initiated it
    assert h.conv.release(effect["id"], "d1", gesture=True)
    h.pump()
    assert [c[0] for c in h.tools.calls] == ["send_message"]


def test_nm1_an_act_held_while_the_person_speaks_waits_and_runs_once_they_finish(store):
    """Review 2, NM1: «hold» means wait. The run gives its batch back, nothing runs while that voice is open, and when
    it ends with no words the batch runs again: the act the person asked for happens — once."""
    from conversation.ear import signals as S
    from conversation.ports import Done
    from conversation.testing.scripted_model import reply
    from tests.conversation.unit.convkit import Harness

    h = Harness(store)
    rose = []

    def other_device_speaks():
        if not rose:
            rose.append(1)
            h.hear(S.VadEdge("d2", "rise", h.clock.mono + 5))

    h.model.script["iv_000001"] = [[other_device_speaks, ToolCall("c", "agenda_add", {"what": "w1"}), Done()],
                                   [reply("w2"), Done()]]
    h.utter([(["w1"], 0)])
    assert h.tools.calls == [] and not h.mouth.orders                   # held: nothing done, nothing said yet
    assert [p.get("reason") for k, lab, p in h.tel.events if k == "conv_run" and lab == "superseded"] == ["held"]
    h.at(h.clock.mono + 500).pump()
    assert h.tools.calls == []                                           # the voice is still open: still waiting
    t = h.clock.mono
    h.hear(S.VadEdge("d2", "fall", t), S.Tick(t + 3000))                 # a cough: no words, the voice ends
    assert [c[0] for c in h.tools.calls] == ["agenda_add"]
    assert [lab for lab, _ in h.closes()] == ["answered"]


def test_nm1_an_act_held_after_the_run_already_acted_stays_as_an_entry_proposed_again(store):
    from conversation.ear import signals as S
    from conversation.ports import Done
    from conversation.testing.scripted_model import reply
    from tests.conversation.unit.convkit import Harness

    h = Harness(store)
    h.model.script["iv_000001"] = [[ToolCall("c1", "agenda_add", {"what": "w1"}), Done()],
                                   [lambda: h.hear(S.VadEdge("d2", "rise", h.clock.mono + 5)),
                                    ToolCall("c2", "agenda_add", {"what": "w2"}), Done()],
                                   [reply("w3"), Done()]]
    h.utter([(["w1"], 0)])
    assert [c[0] for c in h.tools.calls] == ["agenda_add"]               # the first act went; the second was held
    held = [k for k in h.owed.rows if k.startswith("conv:held:")]
    assert held and h.owed.rows[held[0]]["text"] == "held:agenda_add", "the held act was lost"
