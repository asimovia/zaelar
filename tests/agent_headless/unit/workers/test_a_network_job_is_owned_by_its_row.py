"""An agent's question reaches him ONE way (his row, bound by its ask id) and a JOB is owned by a row until it ends.

`nucleo/mesh_jobs`, for any network agent:

  · a question — asked at once by the skill a worker called, or minutes later by a job — goes on a row through THE
    asker (`clarify`), with its declared options and `remote: {thread, question}`; the exchange keeps WHICH question it
    waits on and refuses an answer to any other (audit P2-2); his option goes back by INDEX, words never answer a
    question with options (P3), and only then are its values kept as his (P1-4/P2-1); the request is sent again whole
    and the worker that asked is resumed with what came of it;
  · a job (`202`) gets a row born from the worker's, waiting `remote_job`; its END is read FIRST and only from the
    agent's own `final` (P1-2, P2-5); reached through the relay with the account's credential AND the job's own token
    (the real `_get`/`_post`, only the socket replaced); its result is bounded leaf by leaf, so a long transcript never
    drops the fact that a booking MAY exist (P2-3); with no session to tell, the row ends FAILED, not done; a job given
    up is told as UNKNOWN; a row he ended releases a question it held (P2-7); a relayed job debits the lease once.

Disarm: drop the `ask_id` check in `answered` → red; read questions before `final` in `_tick` → red.
"""
from __future__ import annotations

import asyncio
import io
import json
import time
import urllib.request
from types import SimpleNamespace

import pytest

from memory import db as memdb
from nucleo import mesh_call, mesh_dialog, mesh_jobs

EP = "https://dining.example.test"
Q_JOB = {"status": "NEEDS_INPUT", "final": False, "result": {"questions": [
    {"id": "q1", "ask": "No hay mesa a las 21:00. Ofrecen las 21:30. ¿La aceptas?",
     "choices": [{"id": "accept", "label": "Sí, a las 21:30", "value": "21:30"}, {"id": "decline", "label": "No"}]}]}}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    import rules
    rules._reset_for_tests()
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda *a, **k: None)
    from nucleo.circuit import ledger
    parent = ledger.task_uid("41")
    ledger.store().task_put({"id": parent, "title": "reserva", "goal": "reserva en Casa", "kind": "web", "mode": "now",
                             "state": "running", "visible": True, "origin": "voz", "created_at": 1, "started_at": 1})
    ledger.store().task_patch(parent, session_id="sess-1", cwd="/tmp/w")
    polls, posts, charged, resumed = [], [], [], []
    monkeypatch.setattr(mesh_jobs, "_get", lambda t: polls.pop(0) if polls else {"status": "PENDING", "final": False})
    from nucleo import mesh_agents
    monkeypatch.setattr(mesh_agents, "_post", lambda url, body, timeout=0, bearer=None, headers=None:
                        posts.append((url, body, bearer)) or (202, {"status": "CALLING_BACK"}))
    from nucleo.energy import meter
    monkeypatch.setattr(meter, "report_agent_usage", lambda **k: charged.append(k) or 1.0)
    from nucleo.cli import worker_api_resume
    monkeypatch.setattr(worker_api_resume, "resume_soon",
                        lambda uid, entry, src="": resumed.append((uid, entry, src)) or 5)
    t = {"agent": "dining-agent", "endpoint": EP, "skill": "book-by-phone", "path": "/v1/book-by-phone",
         "via": mesh_call.DIRECT, "errand": "reserva en Casa", "task_id": "41", "body": {}, "order": "41"}
    mesh_dialog.save(t)
    mesh_jobs.opened(t, {"jobId": "j1", "poll": "/v1/jobs/j1", "jobToken": "jt"})
    yield {"thread": t["id"], "polls": polls, "posts": posts, "charged": charged, "resumed": resumed,
           "ledger": ledger, "parent": parent}
    rules._reset_for_tests()


def _row(w):
    return w["ledger"].store().task_get(mesh_dialog.thread(w["thread"])["row"])


def _later():
    return time.time() + 60


def test_the_job_gets_a_row_born_from_the_workers_that_waits_for_it(world):
    mesh_jobs.sweep(now=0)
    row = _row(world)
    assert row["kind"] == "remote_job" and row["waiting_for"] == "remote_job" and row["session_id"] == "sess-1"


def test_its_question_is_bound_by_its_ask_id_and_his_option_goes_back_by_index(world):
    world["polls"].append(Q_JOB)
    mesh_jobs.sweep(now=_later())
    from nucleo.circuit import asker
    from nucleo.cli import worker_api
    art = asker.artefact(_row(world)["id"])
    assert asker.kind_of(art) == "clarify" and art["options"] == ["Sí, a las 21:30", "No"]
    stale = {**art, "ask_id": "mt_old:j1:q1:1"}
    assert not mesh_jobs.answered(art["uid"], stale, "Sí", 0)["ok"]           # a late answer to another round
    assert not world["posts"]
    assert asyncio.run(worker_api.answer(art["ask_id"], "vale, la de las nueve y media"))   # words: asked again
    assert not world["posts"] and mesh_dialog.thread(world["thread"])["asking"] != art["ask_id"]
    art2 = asker.artefact(_row(world)["id"])
    assert asyncio.run(worker_api.answer(art2["ask_id"], "Sí, a las 21:30", choice=0))
    url, body, bearer = world["posts"][-1]
    assert url == f"{EP}/v1/jobs/j1/answers" and body == {"answers": [{"id": "q1", "choice": "accept"}]} and bearer == "jt"
    assert _row(world)["waiting_for"] == "remote_job" and not world["resumed"]


def test_the_end_is_read_first_kept_whole_and_told_by_the_worker_that_started_it(world):
    world["polls"].append({"status": "FAILED", "final": True, "transcript": "x" * 3000,
                           "result": {"bookingMayExist": True, "questions": Q_JOB["result"]["questions"]}})
    mesh_jobs.sweep(now=_later())
    mesh_jobs.sweep(now=_later() + 600)
    assert len(world["resumed"]) == 1 and not world["posts"]                 # no question asked from a final job
    uid, entry, src = world["resumed"][0]
    assert src == "remote_job" and '"bookingMayExist": true' in entry["remote_result"] and "jt" not in entry["remote_result"]
    from nucleo.cli import worker_api_resume
    assert "never as done or as not done" in worker_api_resume.rebrief(world["ledger"].store().task_get(uid), entry)


def test_a_job_that_does_not_say_it_ended_has_not_ended(world):
    world["polls"].append({"status": "CALLING_BACK", "result": {"answerBy": "x"}})
    mesh_jobs.sweep(now=_later())
    assert not world["resumed"] and not mesh_dialog.thread(world["thread"])["job"].get("done")


def test_without_a_session_to_tell_it_the_row_ends_failed_and_a_given_up_job_is_unknown(world, monkeypatch):
    t = mesh_dialog.thread(world["thread"])
    mesh_jobs.sweep(now=0)
    world["ledger"].store().task_patch(_row(world)["id"], session_id="")
    mesh_jobs._end(mesh_dialog.thread(world["thread"]), {"status": "CONFIRMED", "final": True})
    assert _row(world)["state"] == "failed" and not world["resumed"]
    from nucleo.cli import worker_api_resume
    brief = worker_api_resume.rebrief({}, {"remote_result": "{}", "remote_agent": t["agent"], "gave_up": True})
    assert "UNKNOWN" in brief and "MAY exist" in brief


def test_a_row_he_ended_releases_the_question_it_held(world):
    world["polls"].append(Q_JOB)
    mesh_jobs.sweep(now=_later())
    from nucleo import circuit
    circuit.settle(row=_row(world)["id"], state="cancelled", outcome="he stopped it")
    mesh_jobs.sweep(now=_later() + 60)
    assert world["posts"][-1][1] == {"cancel": True} and mesh_dialog.thread(world["thread"])["job"]["done"]


def test_a_relayed_job_debits_the_lease_once_and_is_reached_with_both_tokens(world, monkeypatch):
    t = {**mesh_dialog.thread(world["thread"]), "via": mesh_call.RELAY, "id": None, "job": None}
    mesh_jobs.opened(t, {"jobId": "j2", "poll": "/v1/jobs/j2", "jobToken": "jt2"})
    assert world["charged"] == [{"provider": "dining-agent.book-by-phone", "ref": "j2"}]
    assert mesh_jobs.opened({**t, "id": None}, {"jobId": "j2"})["thread"] == t["id"]   # a retry reuses its thread
    monkeypatch.setenv("ZAELAR_GATEWAY_URL", "https://egress.example.test/v1")
    monkeypatch.setenv("CONTROL_PLANE_SERVICE_TOKEN", "account-credential")
    seen = []

    class _Resp(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: seen.append(req) or _Resp(b'{"final": false}'))
    from nucleo import mesh_agents                                          # the real `_get`, only the socket faked
    url, bearer, headers = mesh_jobs._url(mesh_dialog.thread(t["id"]))
    assert mesh_agents._get(url, bearer=bearer, headers=headers) == {"final": False}
    req = seen[-1]
    assert req.full_url == "https://egress.example.test/p/mesh/dining.example.test/v1/jobs/j2"
    assert req.get_header("Authorization") == "Bearer account-credential" and req.get_header("X-job-token") == "jt2"


def test_a_question_asked_at_once_goes_on_the_workers_row_and_his_option_resends_and_resumes(world, monkeypatch):
    asks = {"status": "NEEDS_MANDATE", "questions": [
        {"id": "seating.any", "text": "¿Alguna mesa imprescindible?", "choices": [
            {"label": "Cualquier mesa", "set": {"seating.any": True}}, {"label": "Terraza", "set": {"seating.must": ["terrace"]}}]}]}
    t = {"agent": "dining-agent", "endpoint": EP, "skill": "book", "path": "/v1/book", "via": mesh_call.DIRECT,
         "errand": "x", "task_id": "41", "body": {"date": "2026-11-27"}, "order": "41",
         "pending": mesh_dialog.questions_in(asks)}
    mesh_dialog.save(t)
    from nucleo.cli import worker_api
    rec = SimpleNamespace(task_id="41", uid=world["parent"], native_sid="sess-1")
    assert not mesh_jobs.ask_for_worker(SimpleNamespace(task_id="99", uid="x", native_sid=""), t["id"])  # not its task
    ask_id = mesh_jobs.ask_for_worker(rec, t["id"])
    assert ask_id and rec.parked and mesh_dialog.thread(t["id"])["asking"] == ask_id
    sent = []
    monkeypatch.setattr(mesh_call, "_send", lambda th: sent.append(dict(th["body"])) or (200, {"status": "CONFIRMED"}))
    from nucleo import routes
    monkeypatch.setattr(routes, "plan", lambda errand, locale=None: routes.store.Plan())
    assert asyncio.run(worker_api.answer(ask_id, "Terraza", choice=1))
    assert sent == [{"date": "2026-11-27", "seating": {"must": ["terrace"]}}]
    assert world["resumed"] and world["resumed"][-1][0] == world["parent"]
    from nucleo import mesh_dialog as dlg
    import rules
    assert rules.value(rules.path(cls="errand.mesh_serve", channel="mesh"),
                       "mesh.mandate:dining-agent/book/seating.any") == {"set": {"seating.must": ["terrace"]}}
    assert dlg.thread(t["id"])["asking"] is None
