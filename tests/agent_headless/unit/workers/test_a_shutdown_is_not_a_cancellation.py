"""V2-877 #2 — a shutdown is not a cancellation: a worker the HOST stops leaves its place the way a crash does.

Measured 2026-11-11 in the sandbox (ES, «hazme una app que me diga la hora en Tokio»): a clean stop (SIGTERM — the same
`should_exit` path as the idle stop's exit) mid-build emitted `worker.cancelled reason=shutdown`, the row settled
`cancelled` (terminal), the generator's not-ran branch discarded the folder and ended the journal entry, so the boot's
`resume_interrupted_generations` read an empty journal, nothing resumed, and the chat box's reopen said «Nothing was
kept to open». Only HIS cancel ends a task; the host stopping is declared data (`workers/ended.SHUTDOWN`), read by the
session's ending (`session_finish.interrupted`) and by the generator's keep-or-discard.

These drive a REAL `WorkerSession` over the REAL generator backend and `generate_widget`; only the headless agent is
a double that runs until it is killed.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import tasks_store as ts

SPEC = "hazme una app que me diga la hora en Tokio"


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    from widgets import generator, generator_folders, paths
    gen_root = tmp_path / "widgets"
    gen_root.mkdir()
    monkeypatch.setattr(paths, "generated_root", lambda: str(gen_root))
    monkeypatch.setattr(paths, "roots", lambda: [str(gen_root)])
    monkeypatch.setattr(generator_folders, "JOBS_FILE", str(tmp_path / "_jobs.json"))

    class _Proc:                                         # what `kill()` terminates, registered as the real one is
        alive = True

        def poll(self):
            return None if self.alive else -15

        def terminate(self):
            self.alive = False

        kill = terminate

        def wait(self, timeout=None):
            return -15

    def _agent(prompt, token="", *, target):            # the headless agent: writes, then runs until it is killed
        proc = _Proc()
        with generator._PROCS_LOCK:
            generator._PROCS[str(token)] = proc
        with open(os.path.join(target, "manifest.json"), "w") as f:
            f.write('{"id": "half')                          # half-written, as a killed agent leaves it
        deadline = time.time() + 10
        while proc.alive and time.time() < deadline:
            time.sleep(0.01)
        with generator._PROCS_LOCK:
            generator._PROCS.pop(str(token), None)
        return False, "generation cancelled"
    monkeypatch.setattr(generator, "_run_agent", _agent)
    from nucleo.agentes import code as _code
    monkeypatch.setattr(_code, "widget_action", lambda req: ("create", ""))
    now = int(time.time())
    ts.task_put({"id": "c9-1", "goal": SPEC, "title": "Tokyo", "kind": "code", "state": "running",
                 "created_at": now, "started_at": now})
    yield {"row": "c9-1", "root": gen_root, "jobs": tmp_path / "_jobs.json"}
    memdb.reset_db()
    mememb.reset()


def _build_then_stop(monkeypatch, reason: str):
    """A real session builds; the host (or he) stops it mid-build; the dispatcher closes its row."""
    from nucleo import dispatch
    from nucleo.circuit import ledger
    from nucleo.workers.providers.generator import GeneratorBackend
    from nucleo.workers import ended
    from nucleo.workers.session import SessionRecord, WorkerSession
    from widgets import generator
    rec = SessionRecord(task_id="g9", goal=SPEC, kind="code", uid="c9-1")
    monkeypatch.setitem(dispatch._SESSIONS, "g9", rec)
    spec = type("S", (), {"model": "", "kind": "code", "task_id": "g9", "env": {"ZAELAR_TASK_REQUEST": SPEC}})()
    s = WorkerSession(GeneratorBackend(), spec, rec)

    async def _go():
        run = asyncio.create_task(s.run(SPEC))
        for _ in range(500):                                 # until the agent is running
            if "g9" in generator._PROCS:
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)
        if reason == ended.SHUTDOWN:                         # the lifespan's ORDERLY shutdown: the real door
            from nucleo.dispatch import control
            rec.session, rec.task = s, run
            await control.stop_all_async(grace=0.1)
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.wait_for(run, timeout=10)
        else:
            await s.stop(grace=0.1, reason=reason)
            await asyncio.wait_for(run, timeout=10)
    asyncio.run(_go())
    ledger.closed(rec)                                       # what the dispatcher does at the end of every session
    return rec


def test_a_host_stop_leaves_a_row_that_resumes_by_id(world, monkeypatch):
    from nucleo.circuit import ledger
    from nucleo.workers import ended
    rec = _build_then_stop(monkeypatch, ended.SHUTDOWN)
    row = ts.task_get(world["row"])
    assert rec.status != "cancelled", "the host stopping is not his cancel"
    assert (row["state"], row["waiting_for"]) == ("waiting", ledger.WORKER), row
    assert int(row["deadline"] or 0) > 0 and int(row.get("attempts") or 0) == 0, "a host stop is not a death"
    assert ended.resumes_by_id(world["row"])
    due = ledger.worker_resumes_due(time.time() + ledger.WORKER_RESUME_AFTER_S + 1)
    assert [r["id"] for r in due] == [world["row"]], "the pulse resumes it by id, as after a crash"


def test_a_host_stop_keeps_the_build_and_its_journal(world, monkeypatch):
    from nucleo.workers import ended
    _build_then_stop(monkeypatch, ended.SHUTDOWN)
    jobs = json.loads(world["jobs"].read_text())
    (wid, job), = jobs.items()
    assert job["interrupted"] is True and job["payload"]["row"] == world["row"] and job["payload"]["spec"] == SPEC
    assert (world["root"] / wid).is_dir(), "the partial folder is kept for the resume"


def test_his_cancel_still_ends_it_and_discards_the_build(world, monkeypatch):
    """The disarm's mirror: HIS stop is an ending — row cancelled, folder and journal gone, exactly as before."""
    from nucleo.workers import ended
    rec = _build_then_stop(monkeypatch, ended.OPERATOR)
    assert rec.status == "cancelled" and ts.task_get(world["row"])["state"] == "cancelled"
    assert json.loads(world["jobs"].read_text() or "{}") == {}
    assert not any(world["root"].iterdir())


def test_the_resumed_build_rebuilds_its_half_written_folder_clean(world, monkeypatch):
    from nucleo.workers import ended
    from widgets import generator
    _build_then_stop(monkeypatch, ended.SHUTDOWN)
    monkeypatch.setattr(generator, "_run_agent", lambda prompt, token="", *, target: (True, ""))
    monkeypatch.setattr(generator, "_validate", lambda wid, stamp_origin=False: (True, ""))
    res = generator.generate_widget(SPEC, token="g10", row=world["row"])
    assert res["ok"] and not res.get("existed"), "a kept half-build is never mistaken for a finished card"


def test_the_boot_leaves_a_rows_build_to_the_rows_resume(world, monkeypatch):
    """Boot: the journal's build that belongs to a row waiting on its worker is the ROW's — never built twice."""
    from nucleo import runstate
    from nucleo.workers import ended
    from widgets import generator, server_api
    _build_then_stop(monkeypatch, ended.SHUTDOWN)
    monkeypatch.setattr(runstate, "blocks_new_work", lambda who="": False)
    built = []
    monkeypatch.setattr(generator, "generate_widget", lambda *a, **k: built.append(a) or {"ok": True, "id": "x"})

    async def _run_generator(kind, wid, call):
        return call()
    monkeypatch.setattr(server_api, "_run_generator", _run_generator)
    asyncio.run(server_api.resume_interrupted_generations())
    assert built == [], "the row's resume by id owns its build"
    assert list(json.loads(world["jobs"].read_text())) , "…and its journal entry stays for it"


def test_the_boot_does_not_bury_a_row_that_waits_on_its_worker(world, monkeypatch):
    """A trace of live sessions left by the stop must not settle as «interrupted» the row that waits to resume."""
    from nucleo.pulse import rehydrate
    from nucleo.workers import ended
    _build_then_stop(monkeypatch, ended.SHUTDOWN)
    monkeypatch.setattr(rehydrate, "snapshot", lambda: {"at": time.time(), "sessions": [
        {"id": "g9", "uid": world["row"], "goal": SPEC, "kind": "code", "status": "running"}]})
    plan = rehydrate.at_boot(schedule=False)
    assert plan["found"] == 0 and ts.task_get(world["row"])["state"] == "waiting"


def test_reopening_it_says_it_was_interrupted_never_that_nothing_was_kept(world, monkeypatch):
    """The chat box's reopen on a row the host stopped: the truth (`chat.ref.interrupted`), never «Nothing was kept»."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from nucleo.workers import ended
    from server import tasks_api
    _build_then_stop(monkeypatch, ended.SHUTDOWN)
    app = FastAPI()
    app.include_router(tasks_api.router)
    got = TestClient(app).post("/api/tasks/reopen", json={"id": world["row"]}).json()
    assert got.get("interrupted") is True and got.get("ok") is False, got
    from pathlib import Path
    js = (Path(__file__).resolve().parents[4] / "frontend/app/components/ChatRef.js").read_text()
    assert 'r.interrupted' in js and 't("chat.ref.interrupted")' in js, "the box paints the truth it is handed"
