"""A4/N3/D8: a confirmation handle is valid only once presented, is spent ONCE, and its spend and the effect's
reservation are ONE transaction (node 13.14).

A handle confirmed before its question was presented is refused; once presented, a gesture spends it and reserves the
effect — the control's accounting, the spend, the seal and the reservation commit together, so a failure in the
middle leaves the handle presented and nothing reserved. A second confirmation finds it spent. The same operation
again returns the SAME effect row. An unknown submission keeps its slot and is never sent again. Without a delegation
a «yes» by voice (no gesture) commits nothing (D8). On sqlite, two confirmations racing from two writers: one effect.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from conversation.gateway.outbox import Claimed, NeedsConfirmation, Refused
from conversation.gateway import dispatch
from conversation.gateway.outbox import Gateway
from conversation.ledger import Book
from conversation.inbox.accounting import outcomes
from conversation.ledger.book import BookTx
from conversation.store import SqliteStore
from conversation.telemetry import Emitter
from conversation.types import Channel, ControlOp
from tests.conversation.unit.gatekit import ACCT, Kit, RecordingTools


def _held_send(k: Kit) -> str:
    d = k.gw.request(k.ctx(k.utterance("iv1")), k.send())
    assert isinstance(d, NeedsConfirmation)
    return d.handle_id


def test_a_handle_counts_only_once_presented_and_is_spent_once(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    hid = _held_send(k)
    assert k.gw.confirm(k.control(ControlOp.CONFIRM, handle=hid)) == Refused("handle_not_presented")
    k.gw.present(hid, "d1")
    first = k.gw.confirm(k.control(ControlOp.CONFIRM, handle=hid))
    assert isinstance(first, Claimed)
    assert k.gw.confirm(k.control(ControlOp.CONFIRM, handle=hid)) == Refused("handle_spent")
    assert len(k.items("effect")) == 1
    assert set(outcomes(store.snapshot(ACCT)).values()) == {"applied"}


def test_the_spend_and_the_reservation_are_one_transaction(store, clock, telemetry, monkeypatch):
    k = Kit(store, clock, telemetry)
    hid = _held_send(k)
    k.gw.present(hid, "d1")
    ctl = k.control(ControlOp.CONFIRM, handle=hid)

    def broken(self, *a, **kw):
        raise RuntimeError("the machine died between the spend and the reservation")

    monkeypatch.setattr(BookTx, "open_unique", broken)
    with pytest.raises(RuntimeError):
        k.gw.confirm(ctl)
    monkeypatch.undo()
    handle = store.snapshot(ACCT).get("items", hid)
    assert handle["state"] == "presented", "the handle was spent without its effect"
    assert not k.items("effect")
    assert isinstance(k.gw.confirm(ctl), Claimed)                         # the same control, replayed: it goes now


def test_the_same_operation_again_is_the_same_effect_row(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    voice = k.utterance("iv1")
    a = k.gw.request(k.ctx(voice), _local())
    b = k.gw.request(k.ctx(voice), _local())
    assert isinstance(a, Claimed) and isinstance(b, Claimed)
    assert a.effect_id == b.effect_id and b.repeat and len(k.items("effect")) == 1


def _local():
    from conversation.ports import ToolCall
    return ToolCall("c", "agenda_add", {"what": "w0001"})


def test_an_unknown_submission_keeps_its_slot_and_is_never_sent_again(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    voice = k.utterance("iv1")
    eid = k.gw.request(k.ctx(voice), _local()).effect_id
    tools = RecordingTools(raise_exc=asyncio.TimeoutError())
    asyncio.run(dispatch.submit(k.gw, tools, eid, 10 ** 9))
    assert store.snapshot(ACCT).get("items", eid)["state"] == "submission_unknown"
    assert asyncio.run(dispatch.submit(k.gw, RecordingTools(), eid, 10 ** 9)) is None
    assert len(tools.calls) == 1
    again = k.gw.request(k.ctx(voice), _local())
    assert again.effect_id == eid and again.repeat
    dispatch.reconcile(k.gw, eid, "provider_accepted", {"seen": True})
    assert store.snapshot(ACCT).get("items", eid)["state"] == "provider_accepted"


def test_a_yes_by_voice_commits_nothing_without_a_delegation(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    hid = _held_send(k)
    k.gw.present(hid, "d1")
    voice_yes = k.control(ControlOp.CONFIRM, handle=hid, gesture=False, channel=Channel.VOICE)
    assert k.gw.confirm(voice_yes) == Refused("not_a_gesture") and not k.items("effect")
    k.gw.delegate(k.control(ControlOp.DELEGATE, scope={"recipients": ["c1"], "channel": "chat",
                                                       "expires_ms": 10 ** 15, "max": 5}))
    assert isinstance(k.gw.confirm(k.control(ControlOp.CONFIRM, handle=hid, gesture=False,
                                             channel=Channel.VOICE)), Claimed)


def test_two_confirmations_racing_from_two_writers_reserve_one_effect(tmp_path, clock, telemetry):
    path = tmp_path / "c.db"
    s1 = SqliteStore(path)
    k = Kit(s1, clock, telemetry)
    hids = []
    for i in range(20):
        d = k.gw.request(k.ctx(k.utterance(f"iv{i}"), run=f"r{i}"), k.send(text=f"w{i}"))
        k.gw.present(d.handle_id, "d1")
        hids.append(d.handle_id)
    s2 = SqliteStore(path)
    em = Emitter(telemetry, clock, ACCT)
    gw2 = Gateway(Book(s2, lambda: k.lease, ACCT, em, clock), ACCT, k.cfg, em, clock, k.ids, k.gw.specs)
    controls = [(k.control(ControlOp.CONFIRM, handle=h), k.control(ControlOp.CONFIRM, handle=h)) for h in hids]
    won = {h: [] for h in hids}

    def run(gw, side):
        for h, pair in zip(hids, controls):
            if isinstance(gw.confirm(pair[side]), Claimed):
                won[h].append(side)

    ts = [threading.Thread(target=run, args=(k.gw, 0)), threading.Thread(target=run, args=(gw2, 1))]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=30)
    assert all(len(w) == 1 for w in won.values()), won
    assert len(k.items("effect")) == 20
    s1.close()
    s2.close()


def test_m2_the_same_send_twice_under_a_delegation_spends_it_once_and_is_one_row(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    k.gw.delegate(k.control(ControlOp.DELEGATE, scope={"recipients": ["c1"], "channel": "chat",
                                                       "expires_ms": 10 ** 15, "max": 1}))
    voice = k.utterance("iv1")
    a = k.gw.request(k.ctx(voice), k.send())
    b = k.gw.request(k.ctx(voice), k.send())
    assert isinstance(a, Claimed) and isinstance(b, Claimed) and a.effect_id == b.effect_id and b.repeat
    dg = [r for r in k.items("delegation")][0]
    assert dg["data"]["used"] == 1 and len(k.items("effect")) == 1


def test_m5_a_confirmation_by_gesture_is_sent_by_the_manager_and_a_stop_withdraws_what_was_claimed(store):
    """The confirmed send goes out on the next pump — nobody has to call dispatch by hand; a stop during a run
    withdraws an effect it claimed and never submitted (audit M5)."""
    from conversation.ports import Done, ToolCall
    from conversation.testing.scripted_model import reply
    from tests.conversation.unit.convkit import Harness
    from tests.conversation.unit.inboxkit import control
    h = Harness(store, script={"iv_000001": [[ToolCall("c", "send_message", {"to": "c1", "via": "chat",
                                                                               "text": "w5"}), Done()],
                                             [reply("w6?"), Done()]]})
    h.utter([(["w1"], 0)])
    handle = [r for _k, r in store.snapshot("acct-test").scan("items") if r["kind"] == "handle"][0]
    assert handle["state"] == "presented"                      # the reply that asked was played on d1
    h.conv.give(control(ControlOp.CONFIRM, 0, "k1", endpoint="d1", gesture=True, handle=handle["id"]))
    h.pump()
    assert [c[0] for c in h.tools.calls] == ["send_message"]
    effect = [r for _k, r in store.snapshot("acct-test").scan("items") if r["kind"] == "effect"][0]
    assert effect["state"] == "delivered"


def test_nm6_a_stop_withdraws_an_effect_the_run_claimed_and_a_hold_kept_from_being_sent(store):
    """Review 2, NM6: the stop half of M5, with an effect that really is claimed and unsent — a hold from another
    device arrived after the claim — when the person says stop: it is withdrawn, never left claimed, never sent."""
    from conversation.gateway import dispatch
    from conversation.ports import Done, ToolCall
    from conversation.testing.scripted_model import reply
    from tests.conversation.unit.convkit import Harness
    from tests.conversation.unit.inboxkit import control
    h = Harness(store)
    stop = control(ControlOp.STOP, 0, "k-stop", endpoint="d1")
    h.model.script["iv_000001"] = [
        [lambda: dispatch.hold(h.conv.gw, "hd", "d2", h.clock.now_ms() + 10, "onset"),
         ToolCall("c", "agenda_add", {"what": "w1"}), Done()],
        [lambda: h.conv.give(stop), reply("w2"), Done()]]
    h.utter([(["w1"], 0)])
    effect = [r for _k, r in store.snapshot("acct-test").scan("items") if r["kind"] == "effect"][0]
    assert effect["state"] == "withdrawn" and h.tools.calls == []
    assert [lab for lab, _ in h.closes()] == ["silent"]
