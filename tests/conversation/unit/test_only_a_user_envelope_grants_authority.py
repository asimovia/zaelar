"""I8/A3: only the person's entries grant authority, judged per effect from the run's batch (node 13.13, plan §15).

A read passes from any batch. An effect rests on a batch that is ALL the person's (the authority floor); a batch caused by a
contact or a worker — or one that mixes the person's sentence with theirs — lends nothing: the effect needs a gesture
(`NeedsConfirmation`) or a mandate. The model's `on` changes nothing. `destructive` and `payment` always need a
gesture; a delegation covers `egress` only, and only a gesture creates one; a grant is created only from an all-user
batch under a covering delegation and matches its exact operation. A refused or held proposal does NOT cut the
writes (E5); a call that reaches dispatch without a reservation does.
"""
from __future__ import annotations

import asyncio

from conversation.gateway import Claimed, NeedsConfirmation, Read, Refused
from conversation.gateway import dispatch
from conversation.ports import ToolCall
from conversation.types import Channel, ControlOp
from tests.conversation.unit.gatekit import Kit, RecordingTools

ADD = ToolCall("c", "agenda_add", {"what": "w0001"})
SCOPE = {"recipients": ["c1"], "channel": "chat", "expires_ms": 10 ** 15, "max": 2}


def test_a_read_passes_from_any_batch(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    for env in (k.contact(), k.worker(), k.utterance("iv1")):
        assert k.gw.request(k.ctx(env), ToolCall("c", "search", {"q": "w1"})) == Read()


def test_a_local_write_rests_only_on_a_batch_that_is_all_the_persons(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    voice, typed, contact = k.utterance("iv1"), k.text("iv2", t=100), k.contact()
    assert isinstance(k.gw.request(k.ctx(voice, typed), ADD), Claimed)          # voice + text: both the person's
    assert isinstance(k.gw.request(k.ctx(contact), ToolCall("c", "agenda_add", {"what": "w2"})), NeedsConfirmation)
    mixed = k.gw.request(k.ctx(k.utterance("iv3"), k.contact()), ToolCall("c", "agenda_add", {"what": "w3"}))
    assert isinstance(mixed, NeedsConfirmation), "a mixed batch lent the contact the person's authority"


def test_a_send_caused_by_a_contact_or_a_worker_needs_a_gesture_and_cuts_nothing(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    for cause in (k.contact(), k.worker()):
        d = k.gw.request(k.ctx(cause), k.send())
        assert isinstance(d, NeedsConfirmation)
    voice = k.utterance("iv1")
    d = k.gw.request(k.ctx(voice, k.contact()), k.send(on=voice.id))            # the model's `on` is a hint only
    assert isinstance(d, NeedsConfirmation)
    assert not k.items("effect") and not k.flags().get("on")
    assert "conv_effect/claimed" not in telemetry.labels()


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


def test_a_grant_needs_an_all_user_batch_and_a_delegation_and_matches_its_exact_operation(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    voice = k.utterance("iv1")
    assert k.gw.grant(k.ctx(voice), "send_message", k.send().args, 10 ** 15) == Refused("no_authority")
    k.gw.delegate(k.control(ControlOp.DELEGATE, scope={**SCOPE, "max": 1}))
    assert k.gw.grant(k.ctx(voice, k.contact()), "send_message", k.send().args, 10 ** 15) == Refused("no_authority")
    assert k.gw.grant(k.ctx(voice), "send_message", k.send().args, 10 ** 15) == Read()
    result = k.worker()
    k.gw.request(k.ctx(k.utterance("iv5")), k.send(text="w0555"))               # spends the delegation's one use
    assert isinstance(k.gw.request(k.ctx(result), k.send()), Claimed)            # the grant: the exact operation
    assert isinstance(k.gw.request(k.ctx(result), k.send(text="w0999")), NeedsConfirmation)


def test_a_call_that_reaches_dispatch_without_a_reservation_cuts_the_writes(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    tools = RecordingTools()
    assert asyncio.run(dispatch.submit(k.gw, tools, "x_never_reserved", 10 ** 9)) is None
    assert k.flags().get("on") and not tools.calls
    assert k.gw.request(k.ctx(k.utterance("iv1")), ADD) == Refused("write_disabled")
    assert k.gw.request(k.ctx(k.utterance("iv2")), ToolCall("c", "search", {})) == Read()   # reads go on
