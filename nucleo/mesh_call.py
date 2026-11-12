"""nucleo/mesh_call.py — put a structured request to ONE declared skill of a network agent, and carry the exchange.

`mesh_agents.serve` is discovery plus one free-text ask of an agent's first skill: the right tool for «who has hotels
in Madrid». A booking is not that. It is a structured request to a skill the caller CHOSE from the agent's card
(`mesh_skills`), it may come back as a question for the operator (`mesh_dialog`), or as a job that finishes minutes
later on its own (`mesh_jobs`). This module is that conversation's client:

    call(agent_id, skill, body)   → the answer, a question (with its thread), or a job being watched
    reply(thread, answers)        → his answers back to the same exchange: the request sent again whole, or the
                                    job's own answers endpoint

Rules it keeps, all inherited:
  · no catalogue: the agent is the one the Oracle returns for the errand under that id; the skill must be DECLARED
    by its card;
  · free skills go direct; a priced one only through the deployment's relay, and only when it can be priced there
    (`mesh_relay.route`); a `402` is reported, never paid;
  · every call leaves its observer row (`mesh_calls.asked`: field NAMES only) and its per-agent outcome;
  · a `409` is the agent refusing to repeat or to act (`duplicate_risk`, `do_not_call`): said as what it is, never
    retried; a `422`/`200` carrying questions is a question, never a failure.
"""
from __future__ import annotations

import json
import time

from nucleo import mesh_dialog as dialog
from nucleo import mesh_relay as relay
from nucleo import mesh_skills as skills

_PREFILL_ROUNDS = 2
#: The request-key convention: set to the thread id when the skill's own declared examples use it and the caller did
#: not. One order, one key — a resend of the same thread can never become a second order.
_KEY_FIELD = "idempotency_key"


# ── which agent ─────────────────────────────────────────────────────────────────────────────────────────────
def _agent(agent_id: str, errand: str) -> dict | None:
    """The agent the Oracle returns for this errand under that id — never one it does not (no catalogue)."""
    if not errand:
        return None
    from nucleo import mesh_agents
    return next((a for a in mesh_agents.find(errand).get("agents") or [] if str(a.get("agent_id")) == agent_id), None)


# ── one call ────────────────────────────────────────────────────────────────────────────────────────────────
def _with_key(card: dict, skill_id: str, body: dict, key: str) -> dict:
    declared = json.dumps((skills.skill_of(card, skill_id) or {}).get("examples") or [], ensure_ascii=False)
    return {**body, _KEY_FIELD: key} if _KEY_FIELD not in body and _KEY_FIELD in declared else body


def _send(t: dict) -> tuple[int, dict | None]:
    """POST the thread's request to its skill, the way the thread says it goes (direct or relay)."""
    from nucleo import mesh_agents
    url = t["endpoint"].rstrip("/") + t["path"]
    bearer = mesh_agents._bearer_for({"agent_id": t["agent"]}, t["endpoint"])
    if t.get("via") == relay.RELAY:
        url, bearer = relay.url(t["endpoint"], t["path"])
    t0 = time.monotonic()
    status, data = mesh_agents._post(url, t["body"], timeout=float(t.get("timeout") or 60), bearer=bearer)
    ms = round((time.monotonic() - t0) * 1000)
    mesh_agents._note_answer({"agent_id": t["agent"]}, status, data)
    from nucleo import mesh_calls                     # never raises
    mesh_calls.asked({"agent_id": t["agent"]}, t["skill"], t["body"], {"ok": 200 <= status < 300}, status, ms)
    return status, data


def call(agent_id: str, skill_id: str, body: dict, *, errand: str = "", task_id: str = "") -> dict:
    """Put `body` to skill `skill_id` of agent `agent_id`. Never raises; never pays. See the module docstring."""
    agent = _agent(str(agent_id or "").strip(), errand)
    if not agent:
        return {"ok": False, "reason": f"«{agent_id}» is not an agent the network returns for this errand — pass his "
                                       "words as `--errand` and an agent_id `find` lists for them"}
    from nucleo import mesh_agents
    endpoint = mesh_agents._endpoint_of(agent)
    card = mesh_agents._card_of(endpoint) or {}
    path = skills.path_of(card, skill_id)
    if not path:
        return {"ok": False, "agent": agent_id, "skills": skills.skills_of(card),
                "reason": f"«{agent_id}» does not declare a skill «{skill_id}» — pick one of `skills`"}
    via, why = relay.route(agent_id, skill_id, skills.is_free(card, skill_id))
    if via == relay.REFUSED:
        return {"ok": False, "agent": agent_id, "skill": skill_id, "priced": True, "reason": why}
    if via == relay.RELAY and not relay.admit():
        return {"ok": False, "agent": agent_id, "skill": skill_id, "reason": "no Energy left to start a priced call"}
    t = {"agent": agent_id, "endpoint": endpoint, "skill": skill_id, "path": path, "via": via,
         "errand": str(errand or "")[:300], "task_id": str(task_id or ""), "timeout": mesh_agents.agent_timeout(agent)}
    from nucleo import mesh_handoff
    if not (body or {}).get("dry_run"):
        t["order"] = mesh_handoff.signature(body or {}, _KEY_FIELD)
        if (same := mesh_handoff.duplicate(agent_id, skill_id, t["order"])):
            return {"ok": False, "agent": agent_id, "skill": skill_id, "duplicate": True, "thread": same["id"],
                    "reason": "this same order was already handed back and its outcome is unknown (possibly made): "
                              f"never place it twice blindly — report it first with `hbmesh report {same['id']} …`"}
    t["id"] = dialog.save(t)
    t["body"] = _with_key(card, skill_id, dict(body or {}), t["id"])
    return _exchange(t)


def _exchange(t: dict) -> dict:
    """Send the thread's request; answer from his standing preferences what the agent asks in a shape he answered
    before (at most `_PREFILL_ROUNDS` times); return the outcome. The thread is saved either way."""
    applied: list[str] = []
    for _ in range(_PREFILL_ROUNDS + 1):
        status, data = _send(t)
        questions = dialog.questions_in(data)
        if not questions:
            break
        body, still, used = dialog.prefill(t["agent"], t["skill"], questions, t["body"])
        if still or not used:
            t["questions"] = still or questions
            break
        t["body"], applied = body, applied + used
    else:
        questions = []
    out = _outcome(t, status, data, questions)
    if applied:
        out["applied_his_standing_answers"] = applied
    dialog.save(t)
    return out


def _outcome(t: dict, status: int, data, questions: list[dict]) -> dict:
    base = {"agent": t["agent"], "skill": t["skill"], "thread": t["id"], "status": status}
    if status == 0:
        return {**base, "ok": False, "reason": f"«{t['agent']}» did not answer"}
    if status == 402:
        return {**base, "ok": False, "payment_required": True, "reason": f"«{t['agent']}» charges for this: not paid"}
    if questions:
        t["questions"] = questions
        return {**base, "ok": False, "agent_asks_user": questions, "next": _ASK_NEXT.format(thread=t["id"])}
    if status == 202 and isinstance(data, dict):
        from nucleo import mesh_jobs
        job = mesh_jobs.opened(t, data)
        if job:
            return {**base, "ok": True, "pending": True, "job": job.get("id"), "data": data, "next": _JOB_NEXT}
    if status == 409:
        return {**base, "ok": False, "conflict": True, "data": data,
                "reason": f"«{t['agent']}» refused to do it again or at all (see `data`): not retried"}
    if not 200 <= status < 300:
        from nucleo.mesh_agents import _what_the_agent_asks_for
        return {**base, "ok": False, "agent_asks": _what_the_agent_asks_for(data),
                "reason": f"«{t['agent']}» answered {status} (see `agent_asks`)"}
    _learn(t)
    from nucleo import mesh_handoff
    handed = mesh_handoff.of(data)
    if handed:
        if t.get("order"):
            mesh_handoff.keep(t, data)
        return {**base, "ok": True, "handed_back": handed, "next": _HANDOFF_NEXT.format(thread=t["id"])}
    return {**base, "ok": True, "data": data}


def _learn(t: dict) -> None:
    """A served skill teaches the playbook route for this kind of errand: `<agent>/<skill>` (the genome's learned layer)."""
    from nucleo import routes as _routes              # `plan` and `learn` never raise
    plan = _routes.plan(t.get("errand") or "")
    if plan and plan.domain:
        _routes.learn(plan.domain, _routes.store.CH_MESH, target=f"{t['agent']}/{t['skill']}",
                      evidence=f"served «{str(t.get('errand') or '')[:60]}»", rank=10)


_ASK_NEXT = ("The agent ASKS the operator before it can go on — it did not refuse. Ask him (bridge `ask`, each "
             "question's `text` with its choices as `--option`, in order), END YOUR TURN, and when resumed send his "
             "answers back: `hbmesh reply {thread} --answer <question id>=<choice number> [--value <what he said>]` "
             "(one `--answer` per question; `--value` only for a choice with `needs_value`). Never pick for him.")
_JOB_NEXT = ("The agent is working on it and will finish on its own (a job). Its outcome and any question it raises "
             "reach the operator by themselves on this task's row: tell him it is in progress, do NOT claim it is "
             "done, and end your turn — do not wait or poll.")


_HANDOFF_NEXT = ("The agent cannot do this itself and HANDS IT BACK (`handed_back`): do it as the operator, following "
                 "`action`. `note` is that platform's own rule — follow it exactly as written; where it forbids "
                 "automation, give him the link. Use only the values in `fields`; a required one that is null is asked "
                 "to him. A captcha, a card, a deposit or fee, a login or a code: take it to that step and hand it to "
                 "him with the link. A form sent to the place itself is a REQUEST, not a booking — say so. Submit ONCE; "
                 "a submit whose result you did not see counts as possibly made. When it ends: "
                 "`hbmesh report {thread} <one of report_as>`. `agent_can_do`, when present, is the agent's own way to "
                 "do it for him: `hbmesh call <agent> <its skill> --json` with its request, if he wants that.")


# ── his answers back ────────────────────────────────────────────────────────────────────────────────────────
def reply(thread_id: str, answers: list[tuple[str, int | None, object]], *, cancel: bool = False) -> dict:
    """His answers to the open questions of thread `thread_id`: `[(question_id, choice_number|None, value|None)]`.
    A choice that can stand as his preference is kept for the next time. Never raises."""
    t = dialog.thread(thread_id)
    if not t:
        return {"ok": False, "reason": f"no open exchange «{thread_id}» (it ended or expired)"}
    if (t.get("job") or {}).get("id"):
        from nucleo import mesh_jobs
        return mesh_jobs.answer(t, answers, cancel=cancel)
    if cancel:
        t["questions"] = []
        dialog.save(t)
        return {"ok": True, "thread": t["id"], "cancelled": True}
    by_id = {q["id"]: q for q in t.get("questions") or []}
    body = t.get("body") or {}
    for qid, n, value in answers:
        q = by_id.get(qid)
        if q is None:
            return {"ok": False, "thread": t["id"], "reason": f"«{qid}» is not one of this exchange's open questions",
                    "open": list(by_id)}
        new, _job_answer, why = dialog.apply(body, q, n, value)
        if new is None:
            return {"ok": False, "thread": t["id"], "reason": why or f"«{qid}» cannot be answered that way"}
        body = new
        if n is not None and value is None:
            dialog.remember(t["agent"], t["skill"], q, n)
    t["body"], t["questions"] = body, []
    return _exchange(t)
