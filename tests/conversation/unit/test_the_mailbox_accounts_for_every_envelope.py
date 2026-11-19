"""I6: every accepted envelope ends accounted for, nothing sits in limbo, and the inbox is durable (node 13.6).

Over both stores: dedupe by (producer, producer_id), the 350 ms collect window, a control applied at once, a control
nobody handles closed by the sweep; only the person's entries are rows here (what is owed lives in its own ledger);
on sqlite, what was accepted survives closing and reopening the store.
"""
from __future__ import annotations

from conversation.config import Config
from conversation.ear import signals as S
from conversation.inbox import Inbox
from conversation.inbox.accounting import audit, outcomes
from conversation.store import SqliteStore
from conversation.telemetry import Emitter
from conversation.types import ControlOp, Ids
from tests.conversation.unit.inboxkit import ACCT, Pipe, control


def _drain(p: Pipe, t: int) -> list:
    batches = []
    while (b := p.at(t).batch()) is not None:
        batches.append(b)
        p.inbox.account([e.id for e in b.envelopes], "told", t)
    return batches


def test_every_envelope_ends_accounted_and_the_audit_finds_no_limbo(store, clock, telemetry):
    p = Pipe(store, clock, telemetry)
    p.signal(S.TypedSubmit("d1", "c1", "w1", 100), S.TypedSubmit("d2", "c2", "w2", 600))
    stop = p.give(control(ControlOp.STOP, 140, "k1")).envelope
    assert audit(store.snapshot(ACCT), 150, p.cfg) == []
    p.inbox.applied(stop.id, 150)                                   # the manager's handler accounts the control
    _drain(p, 1000)
    snap = store.snapshot(ACCT)
    assert audit(snap, 1000, p.cfg, drained=True) == []
    assert sorted(outcomes(snap).values()) == ["applied", "told", "told"]


def test_a_repeat_of_the_same_producer_id_is_one_row_and_an_event(store, clock, telemetry):
    p = Pipe(store, clock, telemetry)
    p.signal(S.TypedSubmit("d1", "c1", "w1", 100))
    adm = p.signal(S.TypedSubmit("d1", "c1", "w1", 120))
    assert adm[0].disposition == "duplicate" and len(p.inbox.rows()) == 1
    assert "conv_inbox/duplicate" in telemetry.labels()


def test_two_texts_inside_the_collect_window_are_one_batch(store, clock, telemetry):
    p = Pipe(store, clock, telemetry)
    p.signal(S.TypedSubmit("d1", "c1", "w1", 100), S.TypedSubmit("d1", "c2", "w2", 400))
    assert p.at(700).batch() is None                 # 300 ms after the last text: still collecting
    b = p.at(750).batch()
    assert [e.body.text for e in b.envelopes] == ["w1", "w2"] and b.reason == "collect_window"
    p.signal(S.TypedSubmit("d1", "c3", "w3", 1200))
    assert [e.body.text for e in p.at(1600).batch().envelopes] == ["w3"]


def test_a_control_is_applied_at_once_and_never_queued(store, clock, telemetry):
    p = Pipe(store, clock, telemetry)
    adm = p.give(control(ControlOp.STOP, 100, "k1"))
    assert adm.disposition == "control" and p.at(1000).batch() is None


def test_what_was_accepted_survives_closing_the_store(tmp_path, clock, telemetry):
    path = tmp_path / "c.db"
    s = SqliteStore(path)
    p = Pipe(s, clock, telemetry)
    p.signal(S.TypedSubmit("d1", "c1", "w1", 100))
    lease = p.lease
    s.close()
    s2 = SqliteStore(path)
    inbox = Inbox(s2, lambda: lease, ACCT, Config(), Emitter(telemetry, clock, ACCT), Ids("r"))
    b = inbox.next_batch(1000)
    assert [e.body.text for e in b.envelopes] == ["w1"]
    s2.close()


def test_a_control_whose_handler_never_ran_is_closed_by_the_sweep_with_its_reason(store, clock, telemetry):
    p = Pipe(store, clock, telemetry)
    env = p.at(100).give(control(ControlOp.CONFIRM, 100, "k1", gesture=True, handle="h-x")).envelope
    assert audit(store.snapshot(ACCT), 100 + p.cfg.control_bound_ms, p.cfg) == []
    assert audit(store.snapshot(ACCT), 101 + p.cfg.control_bound_ms, p.cfg) != []   # the audit sees the limbo
    p.at(100 + p.cfg.control_bound_ms).batch()                                    # the sweep closes it
    snap = store.snapshot(ACCT)
    assert outcomes(snap) == {env.id: "expired"} and audit(snap, 10 ** 6, p.cfg, drained=True) == []
    closed = [pl for k, lab, pl in telemetry.events if lab == "accounted"]
    assert closed[-1]["reason"] == "control_unhandled" and closed[-1]["outcome"] == "expired"


def test_m1_a_producer_not_of_its_kind_or_another_account_is_refused_with_its_reason(store, clock, telemetry):
    """Authority follows the producer: a connector cannot hand in «the person's text», nor anyone an entry of
    another account (audit M1)."""
    from conversation import envelopes as E
    from conversation.types import Channel, EnvelopeKind
    p = Pipe(store, clock, telemetry)
    forged = E.make(EnvelopeKind.USER_TEXT, E.TextBody("iv9", "w1"), producer="connector:chat", producer_id="m1",
                    account=ACCT, onset_ms=0, sealed_ms=0, channel=Channel.TEXT)
    foreign = E.make(EnvelopeKind.USER_TEXT, E.TextBody("iv8", "w2"), producer="chat:d1", producer_id="c1",
                     account="another-account", onset_ms=0, sealed_ms=0, channel=Channel.TEXT)
    assert p.give(forged).disposition == "refused" and p.give(foreign).disposition == "refused"
    assert p.inbox.rows() == []
    refused = [pl for k, lab, pl in telemetry.events if lab == "refused"]
    assert [(r["reason"], r["text"]) for r in refused] == [("producer_not_of_its_kind", "w1"),
                                                           ("not_this_account", "w2")]
