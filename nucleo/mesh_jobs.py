"""nucleo/mesh_jobs.py — the agent's questions on HIS row, and a network agent's JOB owned by a row until it ends.

ONE way an agent's question reaches him — asked at once, from a job, or before his data goes to a page handed back:
THE asker on a task row (`clarify`), one at a time, its declared options; the exchange remembers WHICH question it waits
on (`asking` = its `ask_id`) and refuses any other. His option goes back by INDEX, with no model; only then are its
values kept as his (`mesh_dialog.remember`). A JOB (`202`) is the pulse's: a row born from the worker's, polled with
back-off (slower, never stopped, while a question is open), ended ONLY by the agent's own `final`; the worker that
started it is resumed with the result, bounded leaf by leaf. A row he ended releases its question and the job is still
followed to its end, so a relay can settle it. A relayed job only debits the local lease here, once, when born.
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
    same = next((x for x in dialog.all_threads() if str((x.get("job") or {}).get("id") or "") == jid
                 and not x["job"].get("done") and x["id"] != t.get("id")), None)
    if same:
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
def ask(t: dict, uid: str, rec=None) -> str:
    """Put the exchange's next pending question on row `uid` through THE asker — through the live worker's own record
    when there is one (its session parks and is resumed with what comes of his answer). Returns the ask id."""
    q = (t.get("pending") or [])[0]
    ask_id = f"{t['id']}:{q['id']}:{int(time.time() * 1000)}"
    t.update(row=uid, asking=ask_id)
    dialog.save(t)
    opts, remote = [c["label"] for c in q["choices"]], {"thread": t["id"], "question": q["id"]}
    if rec is not None:
        from nucleo.cli.worker_api_asks import _register_ask
        return _register_ask(rec, q["text"], options=opts, remote=remote, ask_id=ask_id)
    from nucleo.circuit import asker, ledger
    session = str((ledger.store().task_get(uid) or {}).get("session_id") or "")
    asker.ask(uid, {"ask_id": ask_id, "corr_id": ask_id, "uid": uid, "task_id": "", "action": "ask_user",
                    "kind": "clarify", "question": q["text"], "options": opts, "remote": remote, "session": session})
    return ask_id


def ask_for_worker(rec, thread_id: str) -> str:
    """The first question of an exchange a worker's call opened — only an exchange of THIS task with one pending."""
    t = dialog.thread(thread_id)
    if not t or str(t.get("task_id")) != str(getattr(rec, "task_id", "")) or not t.get("pending"):
        return ""
    return ask(t, str(getattr(rec, "uid", "") or ""), rec)


def answered(uid: str, entry: dict, text: str, choice: int | None) -> dict:
    """His answer to the question the exchange waits on (from `worker_api_answer.answer`, off the loop's thread)."""
    remote = entry.get("remote") or {}
    t = dialog.thread(remote.get("thread") or "")
    q = next((q for q in (t or {}).get("pending") or [] if q["id"] == remote.get("question")), None)
    if not t or q is None or t.get("asking") != entry.get("ask_id"):
        return {"ok": False, "reason": "this is not the question that exchange waits on"}
    if q.get("consent"):                               # may his details go to the page the agent handed back?
        if choice is None:
            ask(t, uid)
            return {"ok": False, "asked_again": True}
        t["handoff"]["allowed"], t["pending"], t["asking"] = choice == 0, [], None
        dialog.save(t)
        from nucleo import mesh_handoff
        _tell(t, {"handed_back": t["handoff"].get("view"), "allowed": choice == 0, "your_order": t.get("body")},
              rules=mesh_handoff.NEXT)
        return {"ok": True, "allowed": choice == 0}
    body, job_answer, why = dialog.apply(t.get("body") or {}, q, choice)
    if why:                                            # not one of its options: asked again, nothing sent
        ask(t, uid)
        return {"ok": False, "reason": why, "asked_again": True}
    t["pending"], t["asking"] = [x for x in t["pending"] if x["id"] != q["id"]], None
    dialog.remember(t["agent"], t["skill"], q, choice)          # HIS option, bound by the row's ask id
    if t.get("job"):
        t["job"]["answers"] = (t["job"].get("answers") or []) + [job_answer]
    elif body is not None:
        t["body"] = body
    if t["pending"]:
        ask(t, uid)
        return {"ok": True, "asked_next": True}
    if t.get("job"):
        return _post_answers(t)
    from nucleo import mesh_call
    out = mesh_call.exchange(t)
    if t.get("pending"):
        ask(t, uid)
    elif t.get("job"):                                 # it became a job: the row waits for it, the pulse follows it
        from nucleo.circuit import ledger
        ledger.waiting(uid, WAIT)
    else:
        _tell(t, out)
    return out


def _post_answers(t: dict, cancel: bool = False) -> dict:
    from nucleo import mesh_agents
    from nucleo.circuit import ledger
    url, bearer, headers = _url(t, "/answers")
    body = {"cancel": True} if cancel else {"answers": t["job"].get("answers") or []}
    status, _data = mesh_agents._post(url, body, timeout=_TIMEOUT_S, bearer=bearer or None,
                                      **({"headers": headers} if headers else {}))
    if status == 0 and not cancel:                     # never reached it: kept, sent again at the next beat
        t["job"]["unsent"] = True
    else:
        t["job"].update(answers=[], unsent=False)
    t["job"]["next_at"] = time.time() + POLL_FIRST_S
    if t.get("row") and not cancel:
        ledger.waiting(t["row"], WAIT)
    dialog.save(t)
    return {"ok": 200 <= status < 300, "thread": t["id"], "status": status}


# ── the pulse's sweep ───────────────────────────────────────────────────────────────────────────────────────
def sweep(now: float | None = None) -> int:
    """Advance every open job once (blocking network: the pulse runs this in a thread). Returns how many it touched."""
    now = time.time() if now is None else now
    n = 0
    for t in dialog.all_threads():
        if (t.get("job") or {}).get("id") and not t["job"].get("done"):
            try:
                n += _tick(t, now)
            except Exception as e:  # noqa: BLE001 — one job never stops the others
                _note(e)
    return n


def _tick(t: dict, now: float) -> int:
    job = t["job"]
    if not t.get("row"):
        t["row"] = _open_row(t)
    if not job.get("orphan") and _row_ended(t.get("row") or ""):   # he ended it: release what it held, keep following
        if t.get("asking"):
            _post_answers(t, cancel=True)
        job["orphan"], t["asking"], t["pending"] = True, None, []
    if job.get("unsent"):
        _post_answers(t)
    if now < float(job.get("next_at") or 0):
        dialog.save(t)
        return 0
    data = _get(t)
    if isinstance(data, dict) and data.get("final") is True:     # the END first; any question still open is history
        return _end(t, data)
    if now - float(job.get("since") or now) > GIVE_UP_S:
        return _end(t, {}, gave_up=True)
    if not t.get("asking") and not job.get("orphan") and (questions := dialog.questions_in(data)):
        t["pending"], job["answers"] = questions, []
        ask(t, t["row"])
        return 1
    job["polls"] = int(job.get("polls") or 0) + 1
    job["next_at"] = now + (POLL_MAX_S if t.get("asking") else min(POLL_MAX_S, POLL_EVERY_S * (1 + job["polls"] // 4)))
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
    if uid:
        ledger.store().task_patch(uid, session_id=str(parent.get("session_id") or ""), cwd=str(parent.get("cwd") or ""),
                                  trace_id=str(parent.get("trace_id") or ""), sheet=str(parent.get("sheet") or ""))
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
    t["job"].update(done=True, gave_up=gave_up, ended_at=time.time(), result=_clip(data or {}))
    t.update(asking=None, pending=[], closed=True)
    from nucleo import mesh_handoff
    if mesh_handoff.of(data) is not None:              # a job that ends by handing the step back keeps its guard
        mesh_handoff.keep(t, data)
        t["closed"] = False
        if not t["job"].get("orphan") and (q := mesh_handoff.open_question(t["handoff"]["view"])):
            t["pending"] = [q]
            ask(t, t["row"])
            return 1
    dialog.save(t)
    if not t["job"].get("orphan"):
        _tell(t, data, gave_up=gave_up)
    return 1


def _tell(t: dict, data, *, gave_up: bool = False, rules: str = "") -> None:
    """The worker session that started it is resumed with the outcome, fenced (our rules beside it, outside the fence);
    without one the row ends FAILED with the outcome on it — it was never told to him, and that is not a success."""
    from nucleo import untrusted
    from nucleo.circuit import ledger
    uid = t.get("row") or ""
    row = (ledger.store().task_get(uid) if uid else None) or {}
    result = untrusted.inline(json.dumps(_clip(data or {}), ensure_ascii=False, default=str))
    entry = {"remote_result": result, "remote_agent": t["agent"], "remote_skill": t["skill"], "gave_up": gave_up,
             "remote_rules": rules}
    if row.get("session_id"):
        from nucleo.cli import worker_api_resume as _res
        ledger.resumed(uid)
        if _res.resume_soon(uid, entry, src="remote_job"):
            return
    if uid:
        from nucleo import circuit
        circuit.settle(row=uid, state="failed", outcome=f"{t['agent']} · {t['skill']}: not told — {result}")
