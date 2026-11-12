"""A network agent's JOB is owned by a durable task row until it ends — polled by the pulse, never by a worker.

A skill that answers `202` with a job (a phone call the agent places, say) finishes minutes later. `nucleo/mesh_jobs`:

  · gives the job a ROW of its own, born from the worker's row (its session, so the worker can be resumed), waiting
    `remote_job`;
  · a question the job raises goes on that row through THE asker — `clarify` (dialogue, never a card), its declared
    options, bound to the job by identity (`remote: {thread, question}`); his answer — an option is its INDEX — goes to
    the job's own answers endpoint with no model, and the row waits for the job again;
  · a job bought through the relay is booked by the relay at creation; the engine only debits its lease, ONCE, then;
  · when the job ENDS (read by shape: a `result` with no question) the worker session that started it is resumed
    with the result; the rebrief forbids saying «not booked» for an outcome the agent calls uncertain.

Disarm: drop the `remote` branch in `worker_api_answer.answer` → red; make `_is_final` read `status` words → red.
"""
from __future__ import annotations

import asyncio

import pytest

from memory import db as memdb
from nucleo import mesh_dialog, mesh_jobs, mesh_relay

EP = "https://dining.example.test"


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda *a, **k: None)
    from nucleo.circuit import ledger
    parent = ledger.task_uid("41")
    ledger.store().task_put({"id": parent, "title": "reserva", "goal": "reserva en Casa Pepe", "kind": "web",
                             "mode": "now", "state": "running", "visible": True, "origin": "voz",
                             "created_at": 1, "started_at": 1})
    ledger.store().task_patch(parent, session_id="sess-1", cwd="/tmp/w")
    polls, posts, charged, resumed = [], [], [], []
    monkeypatch.setattr(mesh_jobs, "_get", lambda t: polls.pop(0) if polls else (200, {"status": "PENDING_CALL"}))
    from nucleo import mesh_agents
    monkeypatch.setattr(mesh_agents, "_post", lambda url, body, timeout=0, bearer=None:
                        posts.append((url, body, bearer)) or (202, {"status": "CALLING_BACK"}))
    from nucleo.energy import meter
    monkeypatch.setattr(meter, "report_agent_usage", lambda **k: charged.append(k) or 1.0)
    from nucleo.cli import worker_api_resume
    monkeypatch.setattr(worker_api_resume, "resume_soon", lambda uid, entry, src="": resumed.append((uid, entry, src)) or 5)
    t = {"agent": "tablescout", "endpoint": EP, "skill": "book-by-phone", "path": "/v1/book-by-phone",
         "via": mesh_relay.DIRECT, "errand": "reserva en Casa Pepe", "task_id": "41", "body": {}}
    t["id"] = mesh_dialog.save(t)
    mesh_jobs.opened(t, {"jobId": "j1", "poll": "/v1/jobs/j1", "jobToken": "jt"})
    return {"thread": t["id"], "polls": polls, "posts": posts, "charged": charged, "resumed": resumed,
            "ledger": ledger, "parent": parent}


def _row(w):
    return w["ledger"].store().task_get(mesh_dialog.thread(w["thread"])["row"])


def test_the_job_gets_a_row_born_from_the_workers_that_waits_for_it(world):
    mesh_jobs.sweep(now=0)                                          # before its first poll: only the row
    row = _row(world)
    assert row["kind"] == "remote_job" and row["state"] == "waiting" and row["waiting_for"] == "remote_job"
    assert row["session_id"] == "sess-1" and row["cwd"] == "/tmp/w"
    assert world["ledger"].store().artifact_get(row["id"], "remote")["job"] == "j1"


def test_its_question_is_dialogue_on_the_row_and_his_option_goes_back_by_index(world):
    import time
    world["polls"].append((200, {"status": "NEEDS_INPUT", "result": {"questions": [
        {"id": "q1", "text": "No hay a las 21:00; ¿os vale a las 21:30?", "choices": ["accept", "decline"]}]}}))
    mesh_jobs.sweep(now=time.time() + 60)
    row = _row(world)
    assert row["state"] == "waiting" and row["waiting_for"] == "user_answer"
    from nucleo.circuit import asker
    art = asker.artefact(row["id"])
    assert asker.kind_of(art) == "clarify" and art["options"] == ["accept", "decline"]
    assert art["remote"] == {"thread": world["thread"], "question": "q1"}
    from nucleo.cli import worker_api
    assert asyncio.run(worker_api.answer(art["ask_id"], "accept", choice=0))
    url, body, bearer = world["posts"][-1]
    assert url == f"{EP}/v1/jobs/j1/answers" and body == {"answers": [{"id": "q1", "choice": "accept"}]}
    assert bearer == "jt"                                           # the job's own token, never a client credential
    assert _row(world)["waiting_for"] == "remote_job" and not world["resumed"]   # no worker woken for it


def test_a_relayed_job_debits_the_lease_once_when_it_is_born(world):
    t = mesh_dialog.thread(world["thread"])
    assert world["charged"] == []                                   # a direct (free) job costs nothing here
    mesh_jobs.opened({**t, "via": mesh_relay.RELAY}, {"jobId": "j2", "poll": "/v1/jobs/j2"})
    assert world["charged"] == [{"provider": "tablescout.book-by-phone", "ref": "j2"}]


def test_the_end_is_told_by_the_worker_that_started_it_and_never_charged_again(world):
    import time
    world["polls"].append((200, {"status": "FAILED", "result": {"bookingMayExist": True}}))
    mesh_jobs.sweep(now=time.time() + 60)
    mesh_jobs.sweep(now=time.time() + 600)                          # ended: never polled or told again
    assert world["charged"] == []
    uid, entry, src = world["resumed"][0]
    assert src == "remote_job" and "bookingMayExist" in entry["remote_result"] and len(world["resumed"]) == 1
    from nucleo.cli import worker_api_resume
    brief = worker_api_resume.rebrief(world["ledger"].store().task_get(uid), entry)
    assert "MAY exist" in brief and "never that it did not happen" in brief


def test_a_job_still_working_is_not_ended_by_any_status_word(world):
    import time
    world["polls"].append((200, {"status": "COMPLETED_SOON", "eta": 30}))
    mesh_jobs.sweep(now=time.time() + 60)
    assert not world["resumed"] and not mesh_dialog.thread(world["thread"])["job"].get("done")
