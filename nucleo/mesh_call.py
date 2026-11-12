"""nucleo/mesh_call.py — put a structured request to ONE declared skill of a network agent, and carry the exchange.

`mesh_agents.serve` is discovery plus a free-text ask of an agent's FIRST skill: an agent declaring `search`, `book`
and `book-by-phone` answered every booking errand with a search. Here the caller names a skill its card DECLARES, and
the answer may be a result, a question for the operator (`mesh_dialog`, asked on his row by `mesh_jobs`), a job that
ends later (`mesh_jobs`) or a step handed back to us (`mesh_handoff`). Nothing here names an agent or a skill.

  · **Price is per skill** (its own `pricing`, else the card's; unknown is not free). A free skill goes direct. A priced
    one only through a deployment's relay (`<egress>/p/mesh/<host><path>`, the account's own egress credential) and only
    when the account can PRICE it — a tariff row `agent/<agent>.<skill>`, delivered with the lease. Otherwise refused
    before anything leaves. A `402` is never paid. Self-host has no relay: byte-identical to the free-only rule.
  · **One order, one key.** The request key (`idempotency_key`, set only where the skill's own examples use one) is
    the ENGINE's: derived from the task and the request, never taken from the body or the card. A retry of the same
    order (an answer that never came) carries the same key, so the agent never places it twice.
  · **One order at a time.** While an order of the same task has a step whose outcome is unknown — a send that got no
    answer, an open job, a handed-back step not reported — no OTHER skill of that agent is called for it (no blind
    retry on another channel), and a handed-back step is never asked for twice.
"""
from __future__ import annotations

import hashlib
import json
import urllib.parse

from nucleo import mesh_dialog as dialog

DIRECT, RELAY, REFUSED = "direct", "relay", "refused"
KEY_FIELD = "idempotency_key"
_PREFILL_ROUNDS = 2


# ── the card: one skill, its price ──────────────────────────────────────────────────────────────────────────
def skills_of(card: dict | None) -> list[dict]:
    """The card's skills for a worker's context: `[{id, name, free, describes}]`, in the card's order."""
    return [{"id": s["id"], "name": str(s.get("name") or "")[:80], "free": is_free(card, s["id"]),
             "describes": " ".join(str(s.get("description") or "").split())[:220]}
            for s in ((card or {}).get("skills") or []) if isinstance(s, dict) and str(s.get("id") or "").strip()]


def _skill(card: dict | None, skill_id: str) -> dict | None:
    return next((s for s in ((card or {}).get("skills") or []) if isinstance(s, dict) and skill_id
                 and str(s.get("id") or "").strip() == skill_id), None)


def is_free(card: dict | None, skill_id: str) -> bool:
    """True only when THIS skill's price is unambiguously zero — its own `pricing`, else the card's."""
    from nucleo.mesh_agents import _tier_is_free
    for pricing in ((_skill(card, skill_id) or {}).get("pricing"), (card or {}).get("pricing")):
        verdicts = [_tier_is_free(t) for t in (pricing if isinstance(pricing, list) else [pricing] if pricing else [])]
        if any(v is True for v in verdicts):
            return True
        if any(v is False for v in verdicts):
            return False
    return False


def tariff_key(agent_id: str, skill_id: str) -> str:
    return f"{agent_id}.{skill_id}".lower()


def route(agent_id: str, skill_id: str, free: bool) -> tuple[str, str]:
    """`(DIRECT|RELAY|REFUSED, why)` for one call of this skill (see the module docstring)."""
    from nucleo.energy import egress, tariffs
    if free:
        return DIRECT, ""
    if not (egress.mediated() and egress.credential()):
        return REFUSED, f"«{agent_id}» charges for «{skill_id}» and this engine only uses free skills — nothing was called"
    if not tariffs.has_rate("agent", tariff_key(agent_id, skill_id)):
        return REFUSED, f"«{agent_id}» charges for «{skill_id}» and this account cannot be charged for it — nothing was called"
    return RELAY, ""


def relay_url(endpoint: str, path: str) -> tuple[str, str]:
    """`(url, bearer)` of a relayed call: `<egress>/p/mesh/<host><path>` and this process's egress credential."""
    from nucleo.energy import egress
    return f"{egress.root()}/p/mesh/{urllib.parse.urlsplit(endpoint).netloc}{path}", egress.credential()


# ── one order ───────────────────────────────────────────────────────────────────────────────────────────────
def signature(body: dict) -> str:
    """One request, whatever its key: the body without its key and its dry-run flag."""
    rest = {k: v for k, v in (body or {}).items() if k not in (KEY_FIELD, "dry_run")}
    return hashlib.sha256(json.dumps(rest, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:20]


def _unknown(t: dict) -> bool:
    """Has this thread a step whose outcome nobody knows? (no answer · an open job · a handed-back step unreported)"""
    return (t.get("last_status") == 0 or bool((t.get("job") or {}).get("id") and not t["job"].get("done"))
            or bool(t.get("handoff") and not t["handoff"].get("outcome")))


def _blocking(agent_id: str, skill_id: str, order: str) -> dict | None:
    for t in dialog.all_threads():
        if (t.get("agent"), t.get("order")) == (agent_id, order) and _unknown(t) \
                and (t.get("skill") != skill_id or t.get("handoff")):
            return t
    return None


def _agent(agent_id: str, errand: str) -> dict | None:
    """The agent the Oracle returns for this errand under that id — never one it does not (no catalogue)."""
    if not errand:
        return None
    from nucleo import mesh_agents
    return next((a for a in mesh_agents.find(errand).get("agents") or [] if str(a.get("agent_id")) == agent_id), None)


def call(agent_id: str, skill_id: str, body: dict, *, errand: str = "", task_id: str = "") -> dict:
    """Put `body` to skill `skill_id` of agent `agent_id`. Never raises; never pays."""
    agent = _agent(str(agent_id or "").strip(), errand)
    if not agent:
        return {"ok": False, "reason": f"«{agent_id}» is not an agent the network returns for this errand — pass his "
                                       "words as `--errand` and an agent_id `find` lists for them"}
    from nucleo import mesh_agents
    endpoint = mesh_agents._endpoint_of(agent)
    card = mesh_agents._card_of(endpoint) or {}
    if not _skill(card, skill_id):
        return {"ok": False, "agent": agent_id, "skills": skills_of(card),
                "reason": f"«{agent_id}» does not declare a skill «{skill_id}» — pick one of `skills`"}
    via, why = route(agent_id, skill_id, is_free(card, skill_id))
    if via == REFUSED:
        return {"ok": False, "agent": agent_id, "skill": skill_id, "priced": True, "reason": why}
    body = {k: v for k, v in (body or {}).items() if k != KEY_FIELD}          # the key is never the caller's
    order = str(task_id or "") or signature(body)
    if not body.get("dry_run") and (other := _blocking(agent_id, skill_id, order)):
        return {"ok": False, "agent": agent_id, "duplicate": True, "thread": other["id"],
                "reason": "an earlier step of this same order has no known outcome (possibly done): it is not tried "
                          "again blindly — report it first (`hbmesh report`) or wait for its job"}
    if via == RELAY:
        from nucleo.energy import lease_gate
        if not lease_gate.check("agent"):
            return {"ok": False, "agent": agent_id, "skill": skill_id, "reason": "no Energy left to start a priced call"}
    if KEY_FIELD in json.dumps((_skill(card, skill_id) or {}).get("examples") or []):
        body[KEY_FIELD] = hashlib.sha256(f"{order}|{signature(body)}|{agent_id}|{skill_id}".encode()).hexdigest()[:24]
    t = {"agent": agent_id, "endpoint": endpoint, "skill": skill_id, "path": f"/v1/{skill_id}", "via": via,
         "errand": str(errand or "")[:300], "task_id": str(task_id or ""), "body": body,
         "order": "" if body.get("dry_run") else order, "timeout": mesh_agents.agent_timeout(agent)}
    dialog.save(t)
    return exchange(t)


def exchange(t: dict) -> dict:
    """Send the thread's request; answer from his standing answers what the agent asks in values he chose before (at
    most `_PREFILL_ROUNDS` times); return the outcome. The thread is saved either way."""
    applied: list[str] = []
    for _ in range(_PREFILL_ROUNDS + 1):
        status, data = _send(t)
        questions = dialog.questions_in(data)
        if not questions:
            break
        body, still, used = dialog.prefill(t["agent"], t["skill"], questions, t["body"])
        if still or not used:
            questions = still
            break
        t["body"], applied = body, applied + used
    else:
        questions = []
    out = _outcome(t, status, data, questions)
    if applied:
        out["applied_his_standing_answers"] = applied
    dialog.save(t)
    return out


def _send(t: dict) -> tuple[int, dict | None]:
    from nucleo import mesh_agents
    to = relay_url(t["endpoint"], t["path"]) if t.get("via") == RELAY else None
    res = mesh_agents.ask({"agent_id": t["agent"], "endpoint": t["endpoint"]}, t["skill"], t["body"],
                          timeout=float(t.get("timeout") or 60), path=t["path"], to=to)
    t["last_status"] = int(res.get("status") or (402 if res.get("payment_required") else 0))
    return t["last_status"], res.get("data") if "data" in res else res.get("challenge")


def _outcome(t: dict, status: int, data, questions: list[dict]) -> dict:
    base = {"agent": t["agent"], "skill": t["skill"], "thread": t["id"], "status": status}
    if status == 0:
        return {**base, "ok": False, "reason": f"«{t['agent']}» did not answer; asking again for the SAME order is safe"}
    if status == 402:
        return {**base, "ok": False, "payment_required": True, "reason": f"«{t['agent']}» charges for this: not paid"}
    if questions:
        t["pending"] = questions
        return {**base, "ok": False, "agent_asks_user": [q["text"] for q in questions]}
    if status == 202 and isinstance(data, dict):
        from nucleo import mesh_jobs
        job = mesh_jobs.opened(t, data)
        if job:
            return {**base, "ok": True, "pending": True, "job": job["id"], "thread": job["thread"], "next": _JOB_NEXT}
    if status == 409:
        return {**base, "ok": False, "conflict": True, "data": data,
                "reason": f"«{t['agent']}» refused to do it again or at all (see `data`): not retried"}
    if not 200 <= status < 300:
        from nucleo.mesh_agents import _what_the_agent_asks_for
        return {**base, "ok": False, "agent_asks": _what_the_agent_asks_for(data),
                "reason": f"«{t['agent']}» answered {status} (see `agent_asks`)"}
    from nucleo import mesh_handoff, routes as _routes
    plan = _routes.plan(t.get("errand") or "")          # a served skill teaches the playbook route (`plan`/`learn` never raise)
    if plan and plan.domain:
        _routes.learn(plan.domain, _routes.store.CH_MESH, target=f"{t['agent']}/{t['skill']}",
                      evidence=f"served «{str(t.get('errand') or '')[:60]}»", rank=10)
    if (handed := mesh_handoff.of(data)) is not None:
        mesh_handoff.keep(t, data)
        return {**base, "ok": True, "handed_back": handed, "your_order": t["body"], "next": mesh_handoff.NEXT}
    return {**base, "ok": True, "data": data}


_JOB_NEXT = ("The agent is working on it and finishes on its own (a job): its outcome and any question it raises reach "
             "the operator by themselves. Tell him it is in progress — never that it is done — and end your turn.")
