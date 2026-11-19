"""The reservation of an effect keeps its mechanics while no run reaches it (node 13.33).

F2's door, exercised here directly: `reserve` rests on the batch's authority floor (the person's entries), seals every
intervention of the person's in the batch and reserves ONE row per logical operation, in ONE transaction — a failure
in the middle leaves no seal and no row. The same operation again is the same row; a repeat of a withdrawn one says
so, found by its index. `submit` writes the row ahead before the call; an unknown outcome keeps its slot, is never sent
again and is reconciled by looking; a restart turns `submitting` into `submission_unknown`. A call that reaches
dispatch without a reservation — or a receipt for one — cuts every write of the account while reads go on. On sqlite,
two writers racing for the same operations reserve each one once.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from conversation.gateway import dispatch
from conversation.gateway.outbox import Claimed, Gateway, Read, Refused
from conversation.ledger import Book
from conversation.ledger.book import BookTx
from conversation.ports import ToolCall
from conversation.store import SqliteStore
from conversation.telemetry import Emitter
from conversation.types import ControlOp
from tests.conversation.unit.gatekit import ACCT, Kit, RecordingTools

ADD = ToolCall("c", "agenda_add", {"what": "w0001"})


def _phase(store, iv: str) -> str | None:
    return (store.snapshot(ACCT).get("interventions", iv) or {}).get("phase")


def test_the_seals_and_the_row_are_one_transaction(store, clock, telemetry, monkeypatch):
    k = Kit(store, clock, telemetry)
    voice = k.utterance("iv1")

    def broken(self, *a, **kw):
        raise RuntimeError("the machine died between the seal and the reservation")

    monkeypatch.setattr(BookTx, "open_unique", broken)
    with pytest.raises(RuntimeError):
        k.gw.reserve(k.ctx(voice), ADD)
    monkeypatch.undo()
    assert _phase(store, "iv1") == "closed" and not k.items("effect")      # nothing half done
    got = k.gw.reserve(k.ctx(voice), ADD)
    assert isinstance(got, Claimed) and _phase(store, "iv1") == "sealed"


def test_the_same_operation_again_is_the_same_row(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    voice = k.utterance("iv1")
    a, b = k.gw.reserve(k.ctx(voice), ADD), k.gw.reserve(k.ctx(voice), ADD)
    assert isinstance(a, Claimed) and isinstance(b, Claimed)
    assert a.effect_id == b.effect_id and b.repeat and len(k.items("effect")) == 1


def test_a_batch_without_the_persons_entries_lends_no_authority(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    stop = k.control(ControlOp.STOP)
    assert k.gw.reserve(k.ctx(stop), ADD) == Refused("no_authority") and not k.items("effect")
    assert k.gw.reserve(k.ctx(k.utterance("iv1")), ToolCall("c", "search", {})) == Refused("not_an_effect")


def test_an_unknown_submission_keeps_its_slot_and_is_never_sent_again(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    voice = k.utterance("iv1")
    eid = k.gw.reserve(k.ctx(voice), ADD).effect_id
    tools = RecordingTools(raise_exc=asyncio.TimeoutError())
    asyncio.run(dispatch.submit(k.gw, tools, eid, 10 ** 9))
    assert store.snapshot(ACCT).get("items", eid)["state"] == "submission_unknown"
    assert asyncio.run(dispatch.submit(k.gw, RecordingTools(), eid, 10 ** 9)) is None
    assert len(tools.calls) == 1
    again = k.gw.reserve(k.ctx(voice), ADD)
    assert again.effect_id == eid and again.repeat
    dispatch.reconcile(k.gw, eid, "provider_accepted", {"seen": True})
    assert store.snapshot(ACCT).get("items", eid)["state"] == "provider_accepted"


def test_the_row_is_written_ahead_and_a_restart_never_resends_it(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    eid = k.gw.reserve(k.ctx(k.utterance("iv1")), ADD).effect_id
    seen = []

    class Looking(RecordingTools):
        async def call(self, name, args, **kw):
            seen.append(store.snapshot(ACCT).get("items", eid)["state"])      # what the store says DURING the call
            return await super().call(name, args, **kw)

    asyncio.run(dispatch.submit(k.gw, Looking(), eid, 10 ** 9))
    assert seen == ["submitting"]
    eid2 = k.gw.reserve(k.ctx(k.utterance("iv2")), ToolCall("c", "agenda_add", {"what": "w2"})).effect_id
    with k.book.tx() as b:
        b.move(eid2, "submitting")                                       # the process died inside the call
    assert dispatch.recover(k.gw) == [eid2]
    assert store.snapshot(ACCT).get("items", eid2)["state"] == "submission_unknown"


def test_a_call_that_reaches_dispatch_without_a_reservation_cuts_the_writes(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    tools = RecordingTools()
    assert asyncio.run(dispatch.submit(k.gw, tools, "x_never_reserved", 10 ** 9)) is None
    assert k.flags().get("on") and not tools.calls
    assert k.gw.reserve(k.ctx(k.utterance("iv1")), ADD) == Refused("write_disabled")
    assert k.gw.request(k.ctx(k.utterance("iv2")), ToolCall("c", "search", {})) == Read()   # reads go on
    assert "conv_effect/write_disabled" in telemetry.labels()


def test_a_receipt_for_an_effect_never_reserved_cuts_the_writes(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    dispatch.reconcile(k.gw, "x_never_reserved", "provider_accepted", {"seen": True})
    assert k.flags().get("on")
    assert k.gw.reserve(k.ctx(k.utterance("iv1")), ADD) == Refused("write_disabled")


def test_a_repeat_of_a_withdrawn_effect_says_so_and_finds_it_by_its_index(store, clock, telemetry):
    k = Kit(store, clock, telemetry)
    voice = k.utterance("iv1")
    first = k.gw.reserve(k.ctx(voice), ADD)
    assert isinstance(first, Claimed)
    with k.gw.book.tx() as b:
        b.move(first.effect_id, "withdrawn")
    assert k.gw.reserve(k.ctx(voice), ADD) == Refused("repeat_of_withdrawn")
    assert store.snapshot(ACCT).scan("effect_ops")                      # the index the repeat is read from


def test_two_writers_racing_for_the_same_operations_reserve_each_once(tmp_path, clock, telemetry):
    path = tmp_path / "c.db"
    s1 = SqliteStore(path)
    k = Kit(s1, clock, telemetry)
    ctxs = [k.ctx(k.utterance(f"iv{i}"), run=f"r{i}") for i in range(20)]
    s2 = SqliteStore(path)
    em = Emitter(telemetry, clock, ACCT)
    gw2 = Gateway(Book(s2, lambda: k.lease, ACCT, em, clock), ACCT, k.cfg, em, clock, k.ids, k.gw.specs)
    first: dict[int, list] = {i: [] for i in range(20)}

    def run(gw, side):
        for i, ctx in enumerate(ctxs):
            got = gw.reserve(ctx, ToolCall("c", "agenda_add", {"what": f"w{i}"}))
            if isinstance(got, Claimed) and not got.repeat:
                first[i].append(side)

    ts = [threading.Thread(target=run, args=(k.gw, 0)), threading.Thread(target=run, args=(gw2, 1))]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=30)
    assert all(len(w) == 1 for w in first.values()), first
    assert len(k.items("effect")) == 20
    s1.close()
    s2.close()
