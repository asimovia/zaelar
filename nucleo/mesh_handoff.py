"""nucleo/mesh_handoff.py — an agent that cannot do it itself HANDS IT BACK: «your agent should do it».

A network agent may resolve everything about an errand except the last step — a booking engine it holds no access to,
a restaurant's own form, a phone it does not dial — and answer with a `handoff` object instead of a result: why, the
link (prefilled where the platform allows), the phone, the fields with the operator's values (null = ask him), the
platform's own published restrictions (`providerNote`), the exact client action, and how to report the outcome. This
module is that class, for any agent (nothing here names one, and no platform rule is coded here):

  · `of(answer)` reads it by SHAPE — a `handoff` object that names an action, a link or a phone — into what a worker
    needs, with the agent's phone step (`next`) when it offers one;
  · the exchange keeps it on its THREAD, so the outcome is bound to that order by identity, and an order identical to
    one whose handed-back step has no reported outcome yet is refused (`duplicate`): an unknown submit counts as
    possibly made, so the same restaurant, day, time and party is never sent twice blindly;
  · `report(thread, outcome)` sends the outcome the agent asked for, in its own `reportOutcome` shape, with the
    placeholders filled from its own answer (never personal data of ours).
"""
from __future__ import annotations

import hashlib
import json

from nucleo import mesh_dialog as dialog

def of(data) -> dict | None:
    """The handed-back step, normalised, or None when the answer hands nothing back."""
    h = data.get("handoff") if isinstance(data, dict) else None
    if not isinstance(h, dict) or not (h.get("clientAction") or h.get("bookingUrl") or h.get("phone")):
        return None
    fields = [{"name": str(f.get("name")), "value": f.get("value"), "required": bool(f.get("required"))}
              for f in (h.get("fields") or []) if isinstance(f, dict) and f.get("name")]
    out = {k: v for k, v in {"reason": h.get("reason"), "tier": h.get("tier"), "url": h.get("bookingUrl"),
                              "prefilled": h.get("prefilledFields"), "phone": h.get("phone"), "fields": fields,
                              "note": h.get("providerNote"), "action": h.get("clientAction")}.items()
           if v not in (None, "", [])}
    nxt = data.get("next") if isinstance(data.get("next"), dict) else {}
    if h.get("phoneNext") and nxt.get("path") and isinstance(nxt.get("request"), dict):
        out["agent_can_do"] = {"skill": str(nxt["path"]).rstrip("/").rsplit("/", 1)[-1], "request": nxt["request"]}
    report = h.get("reportOutcome") if isinstance(h.get("reportOutcome"), dict) else {}
    outcome = str((report.get("body") or {}).get("outcome") or "")
    if outcome:
        out["report_as"] = [o for o in outcome.split("|") if o]
    return out


def keep(t: dict, data: dict) -> None:
    """Record the handed-back step on thread `t`: its report contract and the values its placeholders name."""
    report = (data.get("handoff") or {}).get("reportOutcome") or {}
    body = report.get("body") if isinstance(report.get("body"), dict) else {}
    names = [str(v)[1:-1] for v in body.values() if isinstance(v, str) and v.startswith("<") and v.endswith(">")]
    t["handoff"] = {"report": {"method": str(report.get("method") or ""), "path": str(report.get("path") or ""),
                               "body": body}, "refs": {n: data.get(n) for n in names if data.get(n) is not None},
                    "outcome": None}


def signature(body: dict, key_field: str) -> str:
    """One ORDER, whatever its request key: the request without its key and its dry-run flag."""
    rest = {k: v for k, v in (body or {}).items() if k not in (key_field, "dry_run")}
    return hashlib.sha256(json.dumps(rest, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:20]


def duplicate(agent: str, skill: str, order: str) -> dict | None:
    """An open thread for the SAME order whose handed-back step has no reported outcome (possibly made)."""
    for t in dialog.all_threads():
        h = t.get("handoff") or {}
        if (t.get("agent"), t.get("skill"), t.get("order")) == (agent, skill, order) and h and not h.get("outcome"):
            return t
    return None


def report(thread_id: str, outcome: str) -> dict:
    """Tell the agent how its handed-back step ended, in its own `reportOutcome` shape. Never raises."""
    t = dialog.thread(thread_id)
    h = (t or {}).get("handoff") or {}
    rep = h.get("report") or {}
    allowed = [o for o in str((rep.get("body") or {}).get("outcome") or "").split("|") if o]
    if not t or not h:
        return {"ok": False, "reason": f"«{thread_id}» handed nothing back"}
    if outcome not in allowed:
        return {"ok": False, "thread": thread_id, "reason": f"the agent takes one of {allowed}", "report_as": allowed}
    h["outcome"] = outcome                    # recorded first: the order's state is ours whether the agent hears it
    dialog.save(t)
    if rep.get("method", "").upper() != "POST" or not str(rep.get("path") or "").startswith("/"):
        return {"ok": True, "thread": thread_id, "recorded": True, "sent": False}
    body = {k: (outcome if k == "outcome" else h["refs"].get(str(v)[1:-1], v) if isinstance(v, str) else v)
            for k, v in (rep.get("body") or {}).items()}
    from nucleo import mesh_agents
    status, _data = mesh_agents._post(t["endpoint"].rstrip("/") + rep["path"], body)
    return {"ok": True, "thread": thread_id, "recorded": True, "sent": 200 <= status < 300}
