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


def test_the_close_flushes_what_is_left():
    import inspect

    from nucleo.workers import session_events, session_finish
    assert "task_record.flush(rec)" in inspect.getsource(session_finish._closing)
    assert "_record.heard(rec, ev)" in inspect.getsource(session_events._on_event)


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
    from nucleo.memory_agent import writer
    from nucleo.workers import session_finish

    async def _boom(*a, **k):
        raise AssertionError("a second memory writer")
    monkeypatch.setattr(writer, "result", _boom)
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
    (True, "done", "", ["notice:row-5"]),          # a success: the delivery line
    (False, "error", "", []),                      # a failure: the death's question alone (ended.py)
    (False, "relevada", "x", ["notice:row-5"]),    # a relay is not a death
])
def test_a_close_is_told_once(monkeypatch, ok, status, handoff, notices_expected):
    from nucleo.workers import session_finish
    told = _deliver_quiet(monkeypatch)
    rec = _rec()
    rec.ok, rec.status, rec.handoff, rec.result_summary = ok, status, handoff, "No encontré el contacto."
    asyncio.run(session_finish._deliver(rec))
    assert told == notices_expected
    assert task_record.owes_death_notice(rec) is (not ok and not handoff)


def test_disarmed_two_speakers_tell_a_failure_twice(monkeypatch):
    """RED proof: with the shared predicate disarmed, the delivery speaks a failure the death also tells."""
    from nucleo.workers import session_finish
    monkeypatch.setattr(task_record, "owes_death_notice", lambda rec: False)
    told = _deliver_quiet(monkeypatch)
    rec = _rec()
    rec.ok, rec.status, rec.result_summary = False, "error", "No encontré el contacto."
    asyncio.run(session_finish._deliver(rec))
    assert told == ["notice:row-5"]
