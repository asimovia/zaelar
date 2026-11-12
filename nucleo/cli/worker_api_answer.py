"""nucleo/cli/worker_api_answer.py — his answer to a task's DURABLE question (V2-851 §3/§3a), moved by concern out of
`worker_api_asks` (which records the question). The answer is recorded on the question's artefact, a retained act runs
only on his yes (the brief's pick or the row's declared answer, never a word list), the row stops waiting and
the session that asked is resumed by id (`worker_api_resume`). Every name of the registry is read as `_m.<name>`.
"""
from __future__ import annotations

import time

from nucleo import consequence as _consequence
from nucleo.cli.worker_api_asks import _artefact, _keep, _note, open_ask, open_asks


def decision(question: str, text: str, choice: int | None = None, options=None) -> str | None:
    """THE reader of his answer to a durable yes/no question: 'yes' | 'no' | None (not a decision). The binding verdict's
    pick of the declared answers wins (`consent_ask.yes_no`: #0 yes, #1 no); then a reply that IS one of the row's two
    declared answers (`options`, in his language — the screen's buttons send exactly these). Anything else — a longer
    yes, a «no» inside a line, a question back, a correction — is not a decision here: the brief's pick reads it, and a
    no is recorded only when it was read as one (V2-878 §4b: no word table, no second model)."""
    if choice is not None:
        return {0: "yes", 1: "no"}.get(int(choice))
    from nucleo.request import consent_ask as _ca
    return _ca.declared_answer(text, options)


def _says_yes(question: str, text: str, options=None) -> bool:
    """His yes to a retained act (`decision` is 'yes')."""
    return decision(question, text, options=options) == "yes"


def _declined(uid: str, retained: dict) -> None:
    """Record on row `uid` that he said no to its retained act (V2-857): `circuit.close` reads it as the task's
    decision, so the harness never relaunches a worker to do what he refused."""
    if not uid:
        return
    try:
        from nucleo.circuit import DECLINED_SLOT
        from nucleo.circuit import ledger
        inner = (retained.get("payload") or {}) if isinstance(retained.get("payload"), dict) else {}
        ledger.store().artifact_put(uid, DECLINED_SLOT, {"action": str(inner.get("action") or retained.get("action")),
                                                         "at": time.time()})
        from voice.observer import emit
        emit("task", "🙅 he said no to the act — its goal is withdrawn, never retried", text=uid, role="system",
             extra={"cat": "circuit", "task_id": uid, "action": str(retained.get("action") or "")})
    except Exception as ex:  # noqa: BLE001 — the answer itself is recorded either way
        _note(ex)


def says_yes(question: str, text: str, options=None) -> bool:
    """The ONE reader of his yes to a retained act, public for the doors outside this package (the browser click)."""
    return _says_yes(question, text, options)


def _record_for(entry: dict):
    """The live record of the asking session, or a stand-in built from its row (the process ended after asking)."""
    try:
        from nucleo import dispatch
        rec = dispatch.get_record(entry.get("task_id"))
        if rec is not None:
            return rec
    except Exception as e:  # noqa: BLE001
        _note(e)
    from types import SimpleNamespace
    row = {}
    try:
        from nucleo.circuit import ledger
        _ts = ledger.store()
        row = _ts.task_get(entry.get("uid") or "") or {}
    except Exception as e:  # noqa: BLE001
        _note(e)
    return SimpleNamespace(task_id=str(entry.get("task_id") or ""), uid=str(entry.get("uid") or ""),
                           trace_id=str(row.get("trace_id") or ""), surface=str(row.get("surface") or ""),
                           sheet=str(row.get("sheet") or ""), started=float(row.get("started_at") or 0),
                           depth=0, parent_task_id="", kind=str(row.get("kind") or "generic"), goal=str(row.get("goal") or ""))   # checkpoint 1 is read from the row and its spec


#: Why an answer to a question is NOT taken (V2-877 #2) — the one reading the bind door and the answer door share, so
#: the turn never says «passed on» for an answer the answer door refuses.
CLOSED, ANSWERED = "closed", "answered"


def _entry(corr_id: str) -> dict | None:
    """The question `corr_id` as the answer door reads it: this process's entry, else its row's artefact. None when no
    open question has that id."""
    e = _m._ACTS.get(corr_id)
    if e is not None:
        return e
    a = next((a for a in open_asks() if a["ask_id"] == corr_id), None)
    if a is None:
        return None
    uid = a["task_id"]
    e = dict(_artefact(uid)) or {"corr_id": corr_id, "ask_id": corr_id, "uid": uid, "question": a["question"], "retained": {},
                "task_id": ""}
    e.setdefault("uid", uid)
    return e


def refusal(corr_id: str) -> str:
    """"" when an answer to `corr_id` would be taken; else why not: `closed` (no open question has that id) or
    `answered` (its question was already answered — a spent id the row still lists)."""
    e = _entry(corr_id)
    if e is None:
        return CLOSED
    return "" if e.get("state") in (None, "pending") else ANSWERED


async def answer(corr_id: str, text: str, *, resume: bool = True, choice: int | None = None) -> bool:
    """Resolve the question `corr_id` with his `text`: the artefact records the answer, a retained act runs only on his
    yes (`_says_yes`), the row stops waiting and — when the asking session already ended — that session is resumed by
    id with the answer. An INLINE row's question (`nucleo/request/inline_ask`) re-runs its retained act instead, with
    the answer — or the candidate the binding verdict chose (`choice`) — bound. True if an open question was resolved."""
    e = _entry(corr_id)
    if e is None or refusal(corr_id):
        return False
    uid = str(e.get("uid") or "")
    e["answer"] = text or ""
    e["state"] = "answered"
    e["answered_at"] = time.time()
    retained = e.get("retained") or {}
    if e.get("inline"):
        _keep(uid, e)
        try:
            from nucleo.request import inline_ask
            e["result"] = await inline_ask.rerun(uid, e, text, choice)
        except Exception as ex:  # noqa: BLE001
            _note(ex)
        if isinstance(e.get("result"), dict) and e["result"].get("unclear"):
            e.update(state="pending", answer="", answered_at=None)   # not a decision: the question stays open
            _keep(uid, e)
            return False
        return True
    if e.get("remote"):                        # a network agent's job asked it: his answer goes back to THAT job
        from nucleo import mesh_jobs
        _keep(uid, e)
        e["result"] = mesh_jobs.answered(uid, e, text, choice)
        _keep(uid, e)
        return True
    said = decision(str(e.get("question") or ""), text, choice, e.get("options")) if retained.get("action") else None
    if retained.get("action") and said == "no":
        _declined(uid, retained)               # his no ends the act's goal: never a shortfall the circuit retries
    elif retained.get("action") and said is None:
        e["result"] = {"ok": False, "unclear": True}   # neither yes nor no: nothing runs, nothing ends — the session
    elif retained.get("action"):                       # resumes with his words and asks again
        from nucleo.workers import taint as _taint
        rec = _record_for(e)
        _taint.cleared(rec)        # his yes: what the session read before is behind his confirmation (§4a)
        try:
            payload, refused = retained.get("payload") or {}, ""
            from nucleo.workers import exit_gate
            # his yes answers the question, never the door: an act that leaves crosses it again (checkpoint 1, the
            # act's own refusal, his recipient) before it runs; the question it would ask is the one he answered
            if rec is not None and (_ex := await exit_gate.cross(rec, str(retained["action"]), payload)) is not None:
                payload = _ex.payload
                refused = _ex.refused
            if refused:
                e["result"] = {"ok": False, "error": refused}
            else:
                with _taint.during(rec, source=str(retained["action"])):
                    e["result"] = await _m._exec_allow(retained["action"], payload, rec)
            from nucleo.workers import task_files      # his yes ran it: its artefact on the task, at the door
            task_files.record(rec, str(retained["action"]), payload, e["result"])
            task_files.said(rec, str(retained["action"]), payload, e["result"])
        except Exception as ex:  # noqa: BLE001 — `as e` here unbound the entry itself (Python deletes the name)
            _note(ex)
    if corr_id in _m._ACTS:
        _m._ACTS[corr_id] = e
    _keep(uid, e)
    if uid:                                    # `ledger.resumed` owns the row's end of the wait (V2-851 F1a)
        from nucleo.circuit import ledger
        ledger.resumed(uid)
    _m._clear_waiting(str(e.get("task_id") or ""), corr_id)
    if resume and uid:
        try:
            from nucleo.cli import worker_api_resume as _res
            _res.resume_soon(uid, e)
        except Exception as ex:  # noqa: BLE001
            _note(ex)
    return True


async def answer_task(uid: str, ask_id: str, text: str) -> bool:
    """The screen's answer: it names its task and its question. False (→ 409) when that question is not open. A
    screen option IS a declared candidate: picking it is its index, never a reading of words."""
    a = open_ask(uid)
    if a is None or a["ask_id"] != str(ask_id or ""):
        return False
    opts = [str(o) for o in (_artefact(uid).get("options") or [])]
    choice = opts.index(str(text)) if str(text) in opts else None
    return await _m.answer(a["ask_id"], text, choice=choice)


@_consequence.door("worker.answer", neutral=False)
def answer_soon(ask_id: str, text: str, choice: int | None = None) -> bool:
    """Fire-and-forget onto the server loop, from the FlashBrain's job thread: answer the question the turn's verdict
    BOUND (`worker_api_bind`). True if the question was open AND its answer will be taken — the same reading the
    answer door makes (`refusal`): an answer it would refuse is never reported bound, and a spent question is said
    so (`_refused`), never «passed on» (V2-877 #2)."""
    why = refusal(ask_id)
    if why:
        _refused(ask_id, why)
        return False
    try:
        import asyncio

        from nucleo import dispatch
        loop = getattr(dispatch, "_LOOP", None)
        if loop is not None:
            asyncio.run_coroutine_threadsafe(_m.answer(ask_id, text, choice=choice), loop)
        else:
            asyncio.ensure_future(_m.answer(ask_id, text, choice=choice))
        return True
    except Exception as e:  # noqa: BLE001
        _note(e)
        return False


def _refused(ask_id: str, why: str) -> None:
    """An answer the answer door would not take: recorded, and — when its question was already answered — said to him
    once through the out-of-turn mouth, in his language (`answer_already_given`). A closed question says nothing: his
    words were not an answer to anything open. Never raises."""
    try:
        from voice.observer import emit
        emit("task", "🚫 answer not taken — its question is " + why, text=str(ask_id), role="system",
             extra={"cat": "worker_api", "ask_id": str(ask_id), "why": why})
    except Exception as e:  # noqa: BLE001
        _note(e)
    if why != ANSWERED:
        return
    try:
        import asyncio

        from i18n import langs as _l
        from nucleo import dispatch
        from nucleo.pulse import notices
        line = str(getattr(_l.current_language(), "answer_already_given", "") or "")
        if not line:
            return
        coro = notices.notify("zaelar", line, key=f"answer_refused:{ask_id}", kind="info", push_=False)
        loop = getattr(dispatch, "_LOOP", None)
        if loop is not None:
            asyncio.run_coroutine_threadsafe(coro, loop)
        else:
            asyncio.ensure_future(coro)
    except Exception as e:  # noqa: BLE001
        _note(e)


from nucleo.cli import worker_api as _m  # noqa: E402 — last, so importing this module first still resolves
