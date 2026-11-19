"""I6: every accepted envelope ends accounted for, nothing sits in limbo, and the inbox is durable (node 13.6).

Over both stores: dedupe by (producer, producer_id), the 350 ms collect window, progress coalesced, a silent entry
accounted on arrival, a control applied at once, a deferral clamped to the must-tell cap and what must be told
surfaced at that cap even if the manager never goes idle; on sqlite, what was accepted survives closing and
reopening the store.
"""
from __future__ import annotations

from conversation.config import Config
from conversation.ear import signals as S
from conversation.inbox import Inbox
from conversation.inbox.accounting import audit, outcomes
from conversation.store import SqliteStore
from conversation.telemetry import Emitter
from conversation.types import ControlOp, Ids, Surfacing, WorkerUpdate
from tests.conversation.unit.inboxkit import ACCT, Pipe, control, worker


def _drain(p: Pipe, t: int) -> list:
    batches = []
    while (b := p.at(t).batch()) is not None:
        batches.append(b)
        p.inbox.account([e.id for e in b.envelopes], "told", t)
    return batches


def test_every_envelope_ends_accounted_and_the_audit_finds_no_limbo(store, clock, telemetry):
    p = Pipe(store, clock, telemetry)
    p.signal(S.TypedSubmit("d1", "c1", "w1", 100))
    p.give(worker("t1", WorkerUpdate.RESULT, 120, "r1", must_tell=True))
    p.give(worker("t1", WorkerUpdate.PROGRESS, 130, "p1", surfacing=Surfacing.SILENT))
    p.give(control(ControlOp.STOP, 140, "k1"))
    assert audit(store.snapshot(ACCT), 150, p.cfg) == []
    _drain(p, 1000)
    snap = store.snapshot(ACCT)
    assert audit(snap, 1000, p.cfg, drained=True) == []
    assert sorted(outcomes(snap).values()) == ["applied", "silent", "told", "told"]


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


def test_progress_coalesces_and_a_silent_entry_is_accounted_on_arrival(store, clock, telemetry):
    p = Pipe(store, clock, telemetry)
    p.give(worker("t1", WorkerUpdate.PROGRESS, 100, "p1", surfacing=Surfacing.NOW))
    p.give(worker("t1", WorkerUpdate.PROGRESS, 200, "p2", surfacing=Surfacing.NOW))
    p.give(worker("t2", WorkerUpdate.PROGRESS, 210, "p3", surfacing=Surfacing.SILENT))
    b = p.at(300).batch(idle=False)
    assert [e.producer_id for e in b.envelopes] == ["p2"]
    assert sorted(outcomes(store.snapshot(ACCT)).values()) == ["coalesced", "silent"]


def test_a_control_is_applied_at_once_and_never_queued(store, clock, telemetry):
    p = Pipe(store, clock, telemetry)
    adm = p.give(control(ControlOp.STOP, 100, "k1"))
    assert adm.disposition == "control" and p.at(1000).batch() is None


def test_what_must_be_told_is_never_deferred_past_its_cap(store, clock, telemetry):
    cfg = Config(must_tell_max_defer_ms=60_000)
    p = Pipe(store, clock, telemetry, cfg)
    env = p.give(worker("t1", WorkerUpdate.RESULT, 0, "r1", must_tell=True)).envelope
    assert p.at(10).batch(idle=False) is None                   # when idle: not while he is busy…
    b = p.at(20).batch(idle=True)
    p.inbox.defer(env.id, due_ms=10 ** 9, now=20)               # …and a deferral far in the future is clamped
    assert b and [r["due"] for r in p.inbox.rows()] == [60_000]
    assert p.at(59_999).batch(idle=False) is None
    b = p.at(60_000).batch(idle=False)                          # at the cap it is told, idle or not
    assert b is not None and b.envelopes[0].id == env.id


def test_a_when_idle_entry_that_must_be_told_surfaces_at_the_cap_while_busy(store, clock, telemetry):
    cfg = Config(must_tell_max_defer_ms=30_000)
    p = Pipe(store, clock, telemetry, cfg)
    p.give(worker("t9", WorkerUpdate.RESULT, 0, "r9", must_tell=True))
    for t in range(0, 30_000, 5000):
        assert p.at(t).batch(idle=False) is None
    assert p.at(30_000).batch(idle=False) is not None


def test_what_was_accepted_survives_closing_the_store(tmp_path, clock, telemetry):
    path = tmp_path / "c.db"
    s = SqliteStore(path)
    p = Pipe(s, clock, telemetry)
    p.signal(S.TypedSubmit("d1", "c1", "w1", 100))
    lease = p.lease
    s.close()
    s2 = SqliteStore(path)
    inbox = Inbox(s2, lambda: lease, ACCT, Config(), Emitter(telemetry, clock, ACCT), Ids("r"))
    b = inbox.next_batch(1000, idle=True)
    assert [e.body.text for e in b.envelopes] == ["w1"]
    s2.close()
