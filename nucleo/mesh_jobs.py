"""nucleo/mesh_jobs.py — a network agent's JOB, owned by a durable task row until it ends.

Some skills do not answer at once: they accept the work (`202` with a job id) and finish minutes later — a phone call
placed by the agent's own voice assistant, for instance. A worker session must not sit polling for that (its process
is minutes of a model's time, and a restart buries it), so the job is handed to the pulse:

  · `opened(thread, answer)` records the job on its thread (`mesh_dialog`): id, where to poll, its own token;
  · `sweep()` (the pulse, every reconcile beat) gives each open job a ROW of its own the first time it sees it — a
    task the operator sees on his board, born from the worker's row with its session — then polls it, backing off;
  · a job that ASKS (its answer carries `questions`, `mesh_dialog.questions_in`) puts each question on that row
    through THE asker (`nucleo/circuit/asker.ask`, kind `clarify`: dialogue, never a card), one at a time, bound to
    the job by identity (`remote: {thread, question}` on the question's artefact). His answer — a declared option is
    its index, never a reading of words — goes back to the job's own answers endpoint (`answered`), with no model;
  · a job that ENDS resumes the worker session that started it, re-briefed with the job's own result, so the
    outcome is told to him by the session that knows the errand. A result the agent marks as uncertain is said as
    uncertain — the rebrief says so (`worker_api_resume.rebrief`);
  · a job bought through the relay is booked by the relay when it is CREATED (the engine may not be trusted to
    report it); here it only debits the local lease, once, at its tariff row (`report_agent_usage`).

What «ended» means is read from the job's SHAPE, never from its status words: an explicit `final: true` (the A2A
flag), or a `result` object that carries no question.
"""
from __future__ import annotations

import time

from loguru import logger

from nucleo import mesh_dialog as dialog
from nucleo import mesh_relay as relay

WAIT = "remote_job"                      # what a job's row waits for (`ledger.waiting`, named by its writer)
POLL_FIRST_S, POLL_EVERY_S, POLL_MAX_S = 20.0, 30.0, 120.0
GIVE_UP_S = 48 * 3600.0                  # a job silent this long is ended as such — said, never dropped
_GET_TIMEOUT_S = 15.0
_RESULT_MAX = 2500


def _note(e: BaseException) -> None:
    import sys
    logger.debug(f"mesh_jobs: {sys._getframe(1).f_code.co_name} — {type(e).__name__}: {e}")


def opened(t: dict, data: dict) -> dict | None:
    """A `202` that names a job: recorded on thread `t` (saved), polled from now on by `sweep`. None if no job id."""
    jid = data.get("jobId") or data.get("job_id") or data.get("id")
    if not jid:
        return None
    now = time.time()
    t["job"] = {"id": str(jid), "poll": str(data.get("poll") or ""), "token": str(data.get("jobToken") or ""),
                "since": now, "next_at": now + POLL_FIRST_S, "polls": 0, "asked": [], "answers": []}
    dialog.save(t)
    if t.get("via") == relay.RELAY:
        from nucleo.energy import meter
        meter.report_agent_usage(provider=relay.tariff_key(t["agent"], t["skill"]), ref=str(jid))
    return t["job"]


# ── the pulse's sweep ───────────────────────────────────────────────────────────────────────────────────────
def sweep(now: float | None = None) -> int:
    """Advance every open job once (blocking network: the pulse runs this in a thread). Returns how many it touched."""
    now = time.time() if now is None else now
    n = 0
    for t in dialog.open_jobs():
        try:
            n += _tick(t, now)
        except Exception as e:  # noqa: BLE001 — one job never stops the others
            _note(e)
    return n


def _tick(t: dict, now: float) -> int:
    job = t["job"]
    if not t.get("row"):
        t["row"] = _open_row(t)
        dialog.save(t)
    if _row_ended(t.get("row") or ""):
        job["done"] = True                    # he ended its row (or its wait expired): the job is not ours to follow
        dialog.save(t)
        return 0
    if job.get("waiting_answer") or now < float(job.get("next_at") or 0):
        return 0
    status, data = _get(t)
    if now - float(job.get("since") or now) > GIVE_UP_S:
        return _end(t, data if isinstance(data, dict) else {}, gave_up=True)
    questions = dialog.questions_in(data)
    if questions:
        job["pending"] = questions
        job["answers"] = []
        return _ask_next(t)
    if status == 200 and _is_final(data):
        return _end(t, data)
    job["polls"] = int(job.get("polls") or 0) + 1
    job["next_at"] = now + min(POLL_MAX_S, POLL_EVERY_S * (1 + job["polls"] // 4))
    dialog.save(t)
    return 1


def _row_ended(uid: str) -> bool:
    if not uid:
        return False
    from nucleo.circuit import ledger
    row = ledger.store().task_get(uid)
    return bool(row) and str(row.get("state") or "") in ledger.ENDINGS


def _is_final(data) -> bool:
    if not isinstance(data, dict):
        return False
    if data.get("final") is True:                # the A2A status event's own flag
        return True
    return isinstance(data.get("result"), dict) and bool(data["result"]) and not dialog.questions_in(data)


def _url(t: dict, tail: str = "") -> tuple[str, str]:
    """Where this job is reached, and with which bearer: through the relay when it was bought there, else direct with
    the job's own token (never a client credential)."""
    poll = t["job"].get("poll") or f"/v1/jobs/{t['job']['id']}"
    path = (poll if poll.startswith("/") else "/" + poll.split("/", 3)[-1]) + tail
    if t.get("via") == relay.RELAY:
        return relay.url(t["endpoint"], path)
    return t["endpoint"].rstrip("/") + path, t["job"].get("token") or ""


def _get(t: dict) -> tuple[int, dict | None]:
    import json
    import urllib.error
    import urllib.parse
    import urllib.request

    from connectors import outcome as _outcome
    from nucleo.mesh_agents import USER_AGENT
    url, bearer = _url(t)
    headers = {"user-agent": USER_AGENT, **({"authorization": f"Bearer {bearer}"} if bearer else {})}
    req = urllib.request.Request(url, headers=headers)
    try:
        def _go():
            with urllib.request.urlopen(req, timeout=_GET_TIMEOUT_S) as r:
                return r.status, r.read()
        status, raw = _outcome.call(f"mesh:{urllib.parse.urlsplit(url).netloc}", "job", _go,
                                    measure=lambda sb: {"status": sb[0]})
        return status, json.loads(raw.decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "null")
        except Exception:  # noqa: BLE001 — a body that is not JSON is just a status
            return e.code, None
    except Exception as e:  # noqa: BLE001 — a poll that failed is retried at the next beat
        _note(e)
        return 0, None


# ── the row that owns the job ────────────────────────────────────────────────────────────────────────────────
def _open_row(t: dict) -> str:
    """A row for the job, born from the worker's row (same session, cwd, trace, sheet), waiting for the job."""
    from nucleo.circuit import asker, ledger
    parent = ledger.store().task_get(ledger.task_uid(t["task_id"])) if t.get("task_id") else None
    parent = parent or {}
    goal = str(t.get("errand") or parent.get("goal") or f"{t['agent']} · {t['skill']}")
    uid = asker.open_row(goal, kind=WAIT, surface=str(parent.get("surface") or ""),
                         origin=str(parent.get("origin") or "voz"))
    if not uid:
        return ""
    ledger.store().task_patch(uid, session_id=str(parent.get("session_id") or ""), cwd=str(parent.get("cwd") or ""),
                              trace_id=str(parent.get("trace_id") or ""), sheet=str(parent.get("sheet") or ""))
    ledger.store().artifact_put(uid, "remote", {"thread": t["id"], "agent": t["agent"], "skill": t["skill"],
                                                "job": t["job"]["id"]})
    ledger.waiting(uid, WAIT)
    return uid


def _ask_next(t: dict) -> int:
    """Put the next unanswered question of the job on its row (THE asker, dialogue). Returns 1 when one was asked."""
    job, uid = t["job"], t.get("row") or ""
    done = {a.get("id") for a in job.get("answers") or []}
    q = next((q for q in job.get("pending") or [] if q["id"] not in done), None)
    if q is None or not uid:
        dialog.save(t)
        return 0
    from nucleo.circuit import asker, ledger
    from nucleo import untrusted
    row = ledger.store().task_get(uid) or {}
    ask_id = f"{t['id']}:{job['id']}:{q['id']}:{len(job.get('asked') or [])}"
    entry = {"ask_id": ask_id, "corr_id": ask_id, "uid": uid, "task_id": "", "action": "ask_user", "kind": "clarify",
             "question": untrusted.neutralize(q["text"]), "options": [untrusted.neutralize(c["label"]) for c in q["choices"]],
             "remote": {"thread": t["id"], "question": q["id"]}, "session": str(row.get("session_id") or "")}
    job["waiting_answer"] = True
    job.setdefault("asked", []).append(q["id"])
    dialog.save(t)
    asker.ask(uid, entry)
    return 1


def answered(uid: str, entry: dict, text: str, choice: int | None) -> dict:
    """His answer to a job's question (from `worker_api_answer.answer`): a declared option is its index; anything else
    is his words as the answer's value. When the job's questions are all answered they go back to the agent."""
    remote = entry.get("remote") or {}
    t = dialog.thread(remote.get("thread") or "")
    if not t or not t.get("job"):
        return {"ok": False, "reason": "the exchange this question belonged to has ended"}
    q = next((q for q in t["job"].get("pending") or [] if q["id"] == remote.get("question")), None)
    if q is None:
        return {"ok": False, "reason": "the agent no longer asks this"}
    return answer(t, [(q["id"], choice, None if choice is not None else text)])


def answer(t: dict, answers: list[tuple[str, int | None, object]], *, cancel: bool = False) -> dict:
    """Record answers to the job's pending questions; once all are in (or on `cancel`), POST them to the job."""
    job = t["job"]
    by_id = {q["id"]: q for q in job.get("pending") or []}
    for qid, n, value in answers:
        q = by_id.get(qid)
        if q is None:
            return {"ok": False, "thread": t["id"], "reason": f"«{qid}» is not a question this job asks"}
        _body, job_answer, why = dialog.apply({}, q, n, value)
        if job_answer is None:
            return {"ok": False, "thread": t["id"], "reason": why or "that answer does not fit the question"}
        job["answers"] = [a for a in job.get("answers") or [] if a.get("id") != qid] + [job_answer]
    job["waiting_answer"] = False
    if not cancel and {a.get("id") for a in job["answers"]} < set(by_id):
        _ask_next(t)
        return {"ok": True, "thread": t["id"], "recorded": True}
    return _post_answers(t, cancel)


def _post_answers(t: dict, cancel: bool) -> dict:
    from nucleo import mesh_agents
    from nucleo.circuit import ledger
    job = t["job"]
    url, bearer = _url(t, "/answers")
    body = {"cancel": True} if cancel else {"answers": job.get("answers") or []}
    status, data = mesh_agents._post(url, body, timeout=_GET_TIMEOUT_S, bearer=bearer or None)
    job.update(pending=[], answers=[], next_at=time.time() + POLL_FIRST_S)
    if t.get("row"):
        ledger.waiting(t["row"], WAIT)
    dialog.save(t)
    if 200 <= status < 300:
        return {"ok": True, "thread": t["id"], "status": status}
    if status in (409, 410):           # not waiting any more, or past its answer-by time: the job says what it is
        return {"ok": False, "thread": t["id"], "status": status, "data": data,
                "reason": "the agent no longer takes this answer (see `data`); its job reports how it ended"}
    return {"ok": False, "thread": t["id"], "status": status, "reason": f"the agent answered {status or 'nothing'}"}


# ── the end ──────────────────────────────────────────────────────────────────────────────────────────────────
def _end(t: dict, data: dict, *, gave_up: bool = False) -> int:
    job = t["job"]
    job.update(done=True, gave_up=gave_up, ended_at=time.time())
    dialog.save(t)
    _tell(t, data, gave_up)
    return 1


def _tell(t: dict, data: dict, gave_up: bool) -> None:
    """The worker session that started the job is resumed with its result; without one, ONE line says it ended."""
    import json

    from nucleo import untrusted
    from nucleo.circuit import ledger
    uid = t.get("row") or ""
    row = ledger.store().task_get(uid) if uid else None
    result = json.dumps(untrusted.neutralize_tree(data or {}), ensure_ascii=False, default=str)[:_RESULT_MAX]
    entry = {"remote_result": result, "remote_agent": t["agent"], "remote_skill": t["skill"], "gave_up": gave_up}
    if row and row.get("session_id"):
        from nucleo.cli import worker_api_resume as _res
        ledger.resumed(uid)
        if _res.resume_soon(uid, entry, src="remote_job"):
            return
    _say_ended(t, uid)


def _say_ended(t: dict, uid: str) -> None:
    try:
        import asyncio

        from i18n import langs as _l
        from nucleo import circuit, dispatch
        from nucleo.pulse import notices
        if uid:
            circuit.settle(row=uid, state="done", outcome=f"{t['agent']} · {t['skill']}: job ended")
        line = str(getattr(_l.current_language(), "mesh_job_ended", "") or "").format(
            goal=str(t.get("errand") or t["skill"])[:80], agent=t["agent"])
        if not line:
            return
        coro = notices.notify("zaelar", line, key=f"mesh_job:{t['job']['id']}", kind="info")
        loop = getattr(dispatch, "_LOOP", None)
        if loop is not None:
            asyncio.run_coroutine_threadsafe(coro, loop)
        else:
            asyncio.run(coro)
    except Exception as e:  # noqa: BLE001
        _note(e)
