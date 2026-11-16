"""A task's row keeps its record: his mid-task lines, the worker's transcript, ONE memory gate, ONE notice per close.

Measured gaps (Brain Worker plan step 6): what he said mid-task lived only in RAM (`rec.injects`) and was lost on a
restart; the worker's transcript was kept nowhere; two memory writers disagreed (the delivery wrote success only, the
row's close wrote failures too); a failure could be told twice (`notice:<row>` from the delivery and `death:<id>` from
the ending). Each is now one mechanism on the row.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from memory import db as memdb
from nucleo.workers import task_record
from nucleo.workers.session import SessionRecord


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _rec(**kw):
    rec = SessionRecord(task_id="5", goal="crea el grupo cena", uid="row-5")
    for k, v in kw.items():
        setattr(rec, k, v)                      # `verdict` is set on the record by the circuit's close
    return rec


# ── his mid-task lines ───────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("line", ["que sean también Luis y Marta", "also add Luis"])
def test_his_mid_task_line_is_on_the_row_and_outlives_a_restart(fresh_db, monkeypatch, line):
    from nucleo import dispatch
    from nucleo.dispatch import control
    rec = _rec()
    monkeypatch.setattr(dispatch, "_SESSIONS", {"5": rec}, raising=False)
    monkeypatch.setattr(control._d, "_SESSIONS", {"5": rec}, raising=False)
    monkeypatch.setattr(control._d, "resolve_sessions", lambda which: ["5"], raising=False)
    monkeypatch.setattr(control._d._sheets, "recheck_rows", lambda *a, **k: None, raising=False)
    asyncio.run(control.inject("5", line))
    from nucleo.circuit import ledger
    assert [r["text"] for r in ledger.store().artifact_get("row-5", task_record.SAID_SLOT)] == [line]
    fresh = _rec()                                    # a restart: a new record, nothing in RAM
    monkeypatch.setattr(control._d, "_SESSIONS", {"5": fresh}, raising=False)
    assert [s["text"] for s in control.take_pending_injects("5")] == [line], "served from the row"
    assert control.take_pending_injects("5") == [], "delivered once"


def test_a_line_served_from_ram_is_not_served_again_from_the_row(fresh_db):
    task_record.said("row-5", "hola")
    assert task_record.take("row-5", [{"text": "hola"}]) == []
    assert task_record.take("row-5", []) == []


# ── the transcript ───────────────────────────────────────────────────────────────────────────────────────────
def test_the_worker_transcript_is_written_on_the_row_bounded(fresh_db):
    rec = _rec()
    for i in range(task_record.FLUSH_EVERY + 5):
        task_record.heard(rec, SimpleNamespace(type="step", data={"action": "search", "target": f"q{i}"}))
    from nucleo.circuit import ledger
    stored = ledger.store().artifact_get("row-5", task_record.TRANSCRIPT_SLOT)
    assert len(stored) == task_record.FLUSH_EVERY and len(rec.transcript) == 5
    task_record.flush(rec)
    stored = ledger.store().artifact_get("row-5", task_record.TRANSCRIPT_SLOT)
    assert [e["text"] for e in stored][-1] == f"search q{task_record.FLUSH_EVERY + 4}" and not rec.transcript


def test_the_real_event_door_records_and_skips_what_has_no_text(fresh_db):
    """Audit #12 + note 9: through `session_events._on_event` itself; a usage or progress event spends no row."""
    from nucleo.workers import session_events
    rec = _rec()
    door = SimpleNamespace(_rec=rec)
    session_events._on_event(door, SimpleNamespace(type="unseen", data={"text": "read the agenda"}))
    task_record.heard(rec, SimpleNamespace(type="usage", data={"input_tokens": 9}))
    task_record.heard(rec, SimpleNamespace(type="progress", data={}))
    assert [e["text"] for e in rec.transcript] == ["read the agenda"]


def test_a_write_that_did_not_land_keeps_the_buffer(fresh_db, monkeypatch):
    from nucleo.circuit import ledger
    rec = _rec()
    task_record.heard(rec, SimpleNamespace(type="step", data={"text": "x"}))
    monkeypatch.setattr(ledger.store(), "artifact_put", lambda *a, **k: None)   # the store swallows its failure
    task_record.flush(rec)
    assert len(rec.transcript) == 1, "nothing reached the row: nothing left the buffer"


def test_the_close_flushes_what_is_left(fresh_db):
    """Through the real `_closing`: what is buffered reaches the row when the session closes."""
    from nucleo.workers import session_finish
    rec = _rec()
    task_record.heard(rec, SimpleNamespace(type="step", data={"text": "last step"}))
    door = SimpleNamespace(_rec=rec, _usage={}, _usage_partial={})
    try:
        asyncio.run(session_finish._closing(door, rec))
    except Exception:  # noqa: BLE001 — the rest of the close is not this test's; the flush runs first
        pass
    from nucleo.circuit import ledger
    assert [e["text"] for e in ledger.store().artifact_get("row-5", task_record.TRANSCRIPT_SLOT)] == ["last step"]


def test_a_line_served_while_the_inject_yields_is_served_once(fresh_db, monkeypatch):
    """Audit #8: the RAM queue may be served by a bridge call while `inject` awaits the backend."""
    from nucleo.dispatch import control
    from nucleo.workers.session import Inject
    rec = _rec()
    seen = []

    class _Session:
        async def inject(self, text):
            rec.injects.append(Inject(text=text, ts=0.0))
            seen.extend(control.take_pending_injects("5"))     # a bridge call lands in the middle
    rec.session = _Session()
    monkeypatch.setattr(control._d, "_SESSIONS", {"5": rec}, raising=False)
    monkeypatch.setattr(control._d, "resolve_sessions", lambda which: ["5"], raising=False)
    monkeypatch.setattr(control._d._sheets, "recheck_rows", lambda *a, **k: None, raising=False)
    asyncio.run(control.inject("5", "y también Marta"))
    seen.extend(control.take_pending_injects("5"))
    assert [s["text"] for s in seen] == ["y también Marta"]


def test_an_old_undelivered_line_is_not_handed_to_a_later_worker(fresh_db):
    import time
    task_record.said("row-5", "lo de ayer")
    assert task_record.take("row-5", [], now=time.time() + task_record.SAID_MAX_AGE_S + 1) == []
    assert task_record.take("row-5", []) == [], "marked, never served later"


# ── one memory gate ──────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("verdict,state,written", [("met", "done", True), ("unmet", "failed", False),
                                                   ("cannot", "failed", False), ("", "cancelled", False)])
def test_the_close_remembers_only_through_the_one_gate(monkeypatch, verdict, state, written):
    from memory import api as _memory
    from nucleo.circuit import ledger
    wrote = []
    monkeypatch.setattr(_memory, "write", lambda line, **k: wrote.append((line, k)))
    monkeypatch.setattr(_memory, "task_trace_ids", lambda uid: [])
    ledger.remembered(_rec(verdict=verdict, title="Grupo cena"), state=state, outcome="hecho")
    assert bool(wrote) is written
    if written:
        assert wrote[0][1]["kind"] == "result" and wrote[0][1]["meta"]["verdict"] == "met"


def test_the_delivery_writes_no_memory_of_its_own(monkeypatch):
    from memory import api as _memory
    from nucleo.memory_agent import external
    from nucleo.workers import session_finish

    async def _boom(*a, **k):
        raise AssertionError("a second memory writer")
    monkeypatch.setattr(external, "remember", _boom)
    monkeypatch.setattr(_memory, "write", lambda *a, **k: (_ for _ in ()).throw(AssertionError("a second writer")))
    _deliver_quiet(monkeypatch)
    rec = _rec(verdict="met")
    rec.ok, rec.result_summary = True, "Grupo creado."
    asyncio.run(session_finish._deliver(rec))


# ── one notice per close ─────────────────────────────────────────────────────────────────────────────────────
def _deliver_quiet(monkeypatch):
    told = []
    from nucleo.pulse import notices
    from nucleo.workers import spoken_delivery

    async def _notify(*a, **k):
        told.append(k.get("key"))

    async def _line(goal, summary, **k):
        return summary
    monkeypatch.setattr(notices, "notify", _notify)
    monkeypatch.setattr(spoken_delivery, "line", _line)
    return told


@pytest.mark.parametrize("ok,status,handoff,notices_expected", [
    (True, "done", "", ["notice:row-5:5"]),          # a success: the delivery line
    (False, "error", "", ["notice:row-5:5"]),       # a failure WITH a report: its delivery line, no death question
    (False, "relevada", "x", ["notice:row-5:5"]),    # a relay is not a death
])
def test_a_close_is_told_once(monkeypatch, ok, status, handoff, notices_expected):
    from nucleo.workers import session_finish
    told = _deliver_quiet(monkeypatch)
    rec = _rec()
    rec.ok, rec.status, rec.handoff, rec.result_summary = ok, status, handoff, "No encontré el contacto."
    asyncio.run(session_finish._deliver(rec))
    assert told == notices_expected
    assert task_record.owes_death_notice(rec) is False, "a close with something to say is told by its line"
    rec.result_summary = ""
    assert task_record.owes_death_notice(rec) is (not ok and not handoff), "with nothing to say: the death's question"


def test_disarmed_two_speakers_tell_a_failure_twice(monkeypatch):
    """RED proof: with the predicate disarmed (the pre-fix «any failure»), a failure with a report is told twice."""
    import time

    from nucleo.events import task_event
    from nucleo.workers import ended, session_finish
    monkeypatch.setattr(task_record, "owes_death_notice", lambda rec: not rec.ok)
    told = _deliver_quiet(monkeypatch)
    monkeypatch.setattr(task_event, "told", lambda matter, **k: told.append(k.get("key")))
    monkeypatch.setattr(ended, "_bound", lambda: None)
    rec = _rec()
    rec.ok, rec.status, rec.result_summary, rec.started = False, "error", "No encontré el contacto.", time.time()
    asyncio.run(session_finish._deliver(rec))
    ended._remember_ended(rec)
    assert len(told) == 2


# ── exactly one notice, across the conversation's rotation (audit B1) ────────────────────────────────────────
@pytest.mark.parametrize("ok,status,summary,expected", [
    (True, "done", "Grupo creado.", 1), (False, "error", "No encontré el contacto.", 1),
    (False, "error", "", 1), (False, "cancelled", "", 0)])          # his cancel: he already knows
@pytest.mark.parametrize("rotated", [False, True])
def test_a_close_emits_exactly_one_notice_in_total(monkeypatch, ok, status, summary, expected, rotated):
    """Every notice a close can emit, counted: the delivery line AND the death's question, through the real
    ending path — including an errand born before the observability conversation rotated (`_POOL.since`)."""
    import time

    from nucleo.events import task_event
    from nucleo.workers import ended, session_finish
    told = _deliver_quiet(monkeypatch)
    monkeypatch.setattr(task_event, "told", lambda matter, **k: told.append(k.get("key")))
    monkeypatch.setattr(ended, "_bound", lambda: None)
    monkeypatch.setitem(ended._POOL, "since", time.time() + (3600 if rotated else -3600))
    rec = _rec()
    rec.ok, rec.status, rec.result_summary, rec.started = ok, status, summary, time.time()
    if status != "cancelled" and summary:
        asyncio.run(session_finish._deliver(rec))         # `_ending` delivers only a summary that is not a cancel
    ended._remember_ended(rec)
    assert len(told) == expected, told


def test_an_ending_whose_judge_raised_is_still_remembered(monkeypatch):
    """Audit note 10: `circuit.close` that raises returns `undeclared` AND stamps it, so the gate reads a verdict."""
    from nucleo import circuit
    monkeypatch.setattr(circuit, "_close", lambda rec, cap: (_ for _ in ()).throw(RuntimeError("boom")))
    rec = _rec()
    assert circuit.close(rec, 1) == "undeclared" and rec.verdict == "undeclared"


# ── second audit, minors ─────────────────────────────────────────────────────────────────────────────────────────
def test_an_expired_line_is_marked_expired_not_delivered(fresh_db):
    import time
    from nucleo.circuit import ledger
    task_record.said("row-5", "lo de ayer")
    task_record.take("row-5", [], now=time.time() + task_record.SAID_MAX_AGE_S + 1)
    row = ledger.store().artifact_get("row-5", task_record.SAID_SLOT)[0]
    assert row["expired"] is True


def test_the_transcript_buffer_is_bounded_when_the_store_keeps_failing(monkeypatch):
    rec = _rec(uid="")                      # no row: nothing is ever written, the buffer only bounds itself
    for i in range(task_record.TRANSCRIPT_KEPT + 50):
        task_record.heard(rec, SimpleNamespace(type="step", data={"text": f"s{i}"}))
    assert len(rec.transcript) <= task_record.TRANSCRIPT_KEPT


def test_a_line_ending_in_a_space_is_served_once(fresh_db, monkeypatch):
    from nucleo.dispatch import control
    rec = _rec()
    monkeypatch.setattr(control._d, "_SESSIONS", {"5": rec}, raising=False)
    monkeypatch.setattr(control._d, "resolve_sessions", lambda which: ["5"], raising=False)
    monkeypatch.setattr(control._d._sheets, "recheck_rows", lambda *a, **k: None, raising=False)
    asyncio.run(control.inject("5", "y Marta  "))
    assert [s["text"] for s in control.take_pending_injects("5")] == ["y Marta"]
    assert control.take_pending_injects("5") == []


def test_a_failure_whose_judge_raised_is_not_called_done(monkeypatch):
    from nucleo import circuit
    monkeypatch.setattr(circuit, "_close", lambda rec, cap: (_ for _ in ()).throw(RuntimeError("boom")))
    rec = _rec()
    rec.ok = False
    assert circuit.close(rec, 1) == "unmet" and rec.verdict == "unmet"


def test_two_closes_of_one_row_are_two_notices(monkeypatch):
    """A row parked for a quota, then delivered by its next worker: the second notice is not a duplicate."""
    from nucleo.workers import session_finish
    told = _deliver_quiet(monkeypatch)
    for tid in ("5", "6"):
        rec = _rec()
        rec.task_id, rec.ok, rec.status, rec.result_summary = tid, True, "done", "Hecho."
        asyncio.run(session_finish._deliver(rec))
    assert len(set(told)) == 2, told
