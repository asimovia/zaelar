"""nucleo/mesh_jobs.py — the agent's questions on HIS row, and a network agent's JOB owned by a row until it ends.

ONE way an agent's question reaches the operator, whether the agent asked at once (a `422`/`200` with questions) or
minutes later from a job: THE asker, on a task row (`clarify`: dialogue, never a card), one question at a time, its
declared options; the exchange remembers WHICH question it waits on (`asking` = the `ask_id`), and an answer to any
other is refused. His option goes back by INDEX — never a reading of words, never a number a model chose — and only
then are its values kept as his standing answer (`mesh_dialog.remember`). Then the request is sent again whole, or the
job's own answers endpoint is told; with no model.

A JOB (`202` with an id) is the pulse's, never a worker's: `sweep()` gives it a row of its own, born from the worker's
row with its session, polls it with back-off and reads its end by the agent's own `final` flag — a job that does not
say it ended has not ended (GIVE_UP bounds it). When it ends, the worker that started it is resumed with the result,
fenced and never cut where it would lose a fact; a job given up is told as UNKNOWN (it may exist). A job bought through
the relay is booked by the relay; here it only debits the local lease, once, when born.
"""
from __future__ import annotations

import json
import time

from loguru import logger

from nucleo import mesh_dialog as dialog

WAIT = "remote_job"                      # what a job's row waits for (`ledger.waiting`, named by its writer)
POLL_FIRST_S, POLL_EVERY_S, POLL_MAX_S = 20.0, 30.0, 120.0
GIVE_UP_S = 48 * 3600.0
_TIMEOUT_S = 15.0
_LEAF_MAX, _ITEMS_MAX = 400, 40


def _note(e: BaseException) -> None:
    import sys
    logger.debug(f"mesh_jobs: {sys._getframe(1).f_code.co_name} — {type(e).__name__}: {e}")


def opened(t: dict, data: dict) -> dict | None:
    """A `202` that names a job: recorded on thread `t` — or, when the agent answered a retry with a job already being
    followed, that thread's. Returns `{id, thread}`, None when the answer names no job."""
    jid = str(data.get("jobId") or data.get("job_id") or data.get("id") or "")
    if not jid:
        return None
    if (same := dialog.with_job(jid)) and same["id"] != t.get("id"):
        return {"id": jid, "thread": same["id"]}
    now = time.time()
    t["job"] = {"id": jid, "poll": str(data.get("poll") or ""), "token": str(data.get("jobToken") or ""),
                "since": now, "next_at": now + POLL_FIRST_S, "polls": 0, "answers": []}
    dialog.save(t)
    from nucleo import mesh_call
    if t.get("via") == mesh_call.RELAY:
        from nucleo.energy import meter
        meter.report_agent_usage(provider=mesh_call.tariff_key(t["agent"], t["skill"]), ref=jid)
    return {"id": jid, "thread": t["id"]}


# ── his row: the one way a question reaches him ──────────────────────────────────────────────────────────────
def _entry(t: dict, uid: str, session: str) -> dict:
    q = (t.get("pending") or [])[0]
    ask_id = f"{t['id']}:{q['id']}:{int(time.time() * 1000)}"
    t.update(row=uid, asking=ask_id)
    return {"ask_id": ask_id, "corr_id": ask_id, "uid": uid, "task_id": "", "action": "ask_user", "kind": "clarify",
            "question": q["text"], "options": [c["label"] for c in q["choices"]],
            "remote": {"thread": t["id"], "question": q["id"]}, "session": session}


def ask_on_row(t: dict, uid: str) -> str:
    """Put the exchange's next pending question on row `uid` through THE asker. Returns its `ask_id`."""
    from nucleo.circuit import asker, ledger
    entry = _entry(t, uid, str((ledger.store().task_get(uid) or {}).get("session_id") or ""))
    dialog.save(t)
    asker.ask(uid, entry)
    return entry["ask_id"]


def ask_for_worker(rec, thread_id: str) -> str:
    """The FIRST question of an exchange a worker's call opened, on that worker's row: its session parks and is resumed
    with what comes of his answer. Only an exchange of THIS task, with a question pending. Returns the ask id or ""."""
    t = dialog.thread(thread_id)
    if not t or str(t.get("task_id")) != str(getattr(rec, "task_id", "")) or not t.get("pending"):
        return ""
    from nucleo.cli.worker_api_asks import _register_ask
    entry = _entry(t, str(getattr(rec, "uid", "") or ""), "")
    dialog.save(t)
    return _register_ask(rec, entry["question"], options=entry["options"], remote=entry["remote"], ask_id=entry["ask_id"])


def answered(uid: str, entry: dict, text: str, choice: int | None) -> dict:
    """His answer to the question the exchange waits on (from `worker_api_answer.answer`, off the loop's thread)."""
    remote = entry.get("remote") or {}
    t = dialog.thread(remote.get("thread") or "")
    if not t or t.get("asking") != entry.get("ask_id"):
        return {"ok": False, "reason": "this is not the question that exchange waits on"}
    q = next(q for q in t.get("pending") or [] if q["id"] == remote.get("question"))
    body, job_answer, why = dialog.apply(t.get("body") or {}, q, choice, "" if choice is not None else text)
    if why:                                            # not an option of a question that has options: ask it again
        ask_on_row(t, uid)
        return {"ok": False, "reason": why, "asked_again": True}
    t["pending"], t["asking"] = [x for x in t["pending"] if x["id"] != q["id"]], None
    if choice is not None:
        dialog.remember(t["agent"], t["skill"], q, choice)      # HIS option, bound by the row's ask id
    if t.get("job"):
        t["job"]["answers"] = (t["job"].get("answers") or []) + [job_answer]
    elif body is not None:
        t["body"] = body
    if t["pending"]:
        ask_on_row(t, uid)
        return {"ok": True, "asked_next": True}
    if t.get("job"):
        return _post_answers(t)
    from nucleo import mesh_call
    out = mesh_call.exchange(t)
    if t.get("pending"):
        ask_on_row(t, uid)
    elif t.get("job"):                                 # it became a job: the row waits for it, the pulse follows it
        from nucleo.circuit import ledger
        ledger.waiting(uid, WAIT)
    else:
        _tell(t, out, gave_up=False)
    return out


def _post_answers(t: dict, cancel: bool = False) -> dict:
    from nucleo import mesh_agents
    from nucleo.circuit import ledger
    url, bearer, headers = _url(t, "/answers")
    body = {"cancel": True} if cancel else {"answers": t["job"].get("answers") or []}
    status, data = mesh_agents._post(url, body, timeout=_TIMEOUT_S, bearer=bearer or None,
                                     **({"headers": headers} if headers else {}))
    t["job"].update(answers=[], next_at=time.time() + POLL_FIRST_S)
    t["pending"] = []
    if t.get("row") and not cancel:
        ledger.waiting(t["row"], WAIT)
    dialog.save(t)
    return {"ok": 200 <= status < 300, "thread": t["id"], "status": status,
            **({} if 200 <= status < 300 else {"reason": "the agent no longer takes this answer; the job says how it ends"})}


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
    if _row_ended(t.get("row") or ""):                 # he ended it (or its wait expired): release what it held
        if t.get("asking"):
            _post_answers(t, cancel=True)
        job["done"] = True
        dialog.save(t)
        return 1
    if t.get("asking") or now < float(job.get("next_at") or 0):
        return 0
    data = _get(t)
    if now - float(job.get("since") or now) > GIVE_UP_S:
        return _end(t, {}, gave_up=True)
    if isinstance(data, dict) and data.get("final") is True:     # the end FIRST: a question in a final job is history
        return _end(t, data)
    if (questions := dialog.questions_in(data)):
        t["pending"], job["answers"] = questions, []
        ask_on_row(t, t["row"])
        return 1
    job["polls"] = int(job.get("polls") or 0) + 1
    job["next_at"] = now + min(POLL_MAX_S, POLL_EVERY_S * (1 + job["polls"] // 4))
    dialog.save(t)
    return 1


def _row_ended(uid: str) -> bool:
    from nucleo.circuit import ledger
    row = ledger.store().task_get(uid) if uid else None
    return bool(row) and str(row.get("state") or "") in ledger.ENDINGS


def _url(t: dict, tail: str = "") -> tuple[str, str, dict]:
    """Where this job is reached: `(url, bearer, headers)`. Direct, with the job's own token; through the relay when it
    was bought there, with the account's credential AND the job's own token beside it (`X-Job-Token`) — the relay
    reaches the job with that token, so one account never reads another's. Never a client credential."""
    from nucleo import mesh_call
    poll = t["job"].get("poll") or f"/v1/jobs/{t['job']['id']}"
    path = (poll if poll.startswith("/") else "/" + poll.split("/", 3)[-1]) + tail
    token = t["job"].get("token") or ""
    if t.get("via") == mesh_call.RELAY:
        url, credential = mesh_call.relay_url(t["endpoint"], path)
        return url, credential, ({"X-Job-Token": token} if token else {})
    return t["endpoint"].rstrip("/") + path, token, {}


def _get(t: dict) -> dict | None:
    from nucleo import mesh_agents
    url, bearer, headers = _url(t)
    return mesh_agents._get(url, timeout=_TIMEOUT_S, bearer=bearer or None, **({"headers": headers} if headers else {}))


def _open_row(t: dict) -> str:
    """A row for the job, born from the worker's row (same session, cwd, trace, sheet), waiting for the job."""
    from nucleo.circuit import asker, ledger
    parent = (ledger.store().task_get(ledger.task_uid(t["task_id"])) if t.get("task_id") else None) or {}
    uid = asker.open_row(str(t.get("errand") or parent.get("goal") or f"{t['agent']} · {t['skill']}"), kind=WAIT,
                         surface=str(parent.get("surface") or ""), origin=str(parent.get("origin") or "voz"))
    if not uid:
        return ""
    ledger.store().task_patch(uid, session_id=str(parent.get("session_id") or ""), cwd=str(parent.get("cwd") or ""),
                              trace_id=str(parent.get("trace_id") or ""), sheet=str(parent.get("sheet") or ""))
    ledger.store().artifact_put(uid, "remote", {"thread": t["id"], "agent": t["agent"], "skill": t["skill"],
                                                "job": t["job"]["id"]})
    ledger.waiting(uid, WAIT)
    return uid


# ── the end ──────────────────────────────────────────────────────────────────────────────────────────────────
def _clip(v):
    """A stranger's answer bounded LEAF by leaf — never cut as text, which drops the facts at its tail."""
    if isinstance(v, str):
        return v[:_LEAF_MAX]
    if isinstance(v, list):
        return [_clip(x) for x in v[:_ITEMS_MAX]]
    if isinstance(v, dict):
        return {str(k)[:80]: _clip(x) for k, x in list(v.items())[:_ITEMS_MAX] if k not in ("jobToken", "token")}
    return v


def _end(t: dict, data: dict, *, gave_up: bool = False) -> int:
    t["job"].update(done=True, gave_up=gave_up, ended_at=time.time())
    from nucleo import mesh_handoff
    if mesh_handoff.of(data) is not None:              # a job that ends by handing the step back keeps its guard
        mesh_handoff.keep(t, data)
    dialog.save(t)
    _tell(t, data, gave_up)
    return 1


def _tell(t: dict, data, gave_up: bool) -> None:
    """The worker session that started it is resumed with the outcome, fenced; without one the row ends FAILED with the
    outcome on it — it was never told to him, and that is not a success."""
    from nucleo import untrusted
    from nucleo.circuit import ledger
    uid = t.get("row") or ""
    row = (ledger.store().task_get(uid) if uid else None) or {}
    result = untrusted.inline(json.dumps(_clip(data or {}), ensure_ascii=False, default=str))
    entry = {"remote_result": result, "remote_agent": t["agent"], "remote_skill": t["skill"], "gave_up": gave_up}
    if row.get("session_id"):
        from nucleo.cli import worker_api_resume as _res
        ledger.resumed(uid)
        if _res.resume_soon(uid, entry, src="remote_job"):
            return
    if uid:
        from nucleo import circuit
        circuit.settle(row=uid, state="failed", outcome=f"{t['agent']} · {t['skill']}: not told — {result[:300]}")
