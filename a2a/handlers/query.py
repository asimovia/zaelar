"""query → reply | denied, for any declared item and projection. What leaves is decided by the item's projection;
the row logs field NAMES and counts, never values."""
from __future__ import annotations

from ..envelope import EnvelopeError
from ..items import UnknownItem


def _shape(data) -> tuple[int, list[str]]:
    if isinstance(data, list):
        return len(data), sorted({k for x in data if isinstance(x, dict) for k in x})[:12]
    if isinstance(data, dict):
        return len(data), sorted(data)[:12]
    return (0 if data is None else 1), []


def on_query(agent, env) -> None:
    r = agent.rels.get(env.frm)
    b = env.body
    qid, item, proj = str(b.get("qid", ""))[:16], str(b.get("item", ""))[:64], str(b.get("projection") or "default")
    args = b.get("args") if isinstance(b.get("args"), dict) else {}
    agent.emit("query", r=r, dir="in", item=item, projection=proj, args=sorted(args)[:8])
    d = agent.grants.allowed(r.contact_id, item, "see")
    if not d.allowed:
        agent.emit("denied", r=r, dir="out", ok=False, item=item, reason=d.reason)
        agent._send(r, "denied", {"qid": qid, "item": item, "reason": d.reason})
        return
    try:
        data = agent.items.get(item).read(proj, args)
    except UnknownItem:
        agent.emit("denied", r=r, dir="out", ok=False, item=item, reason="unknown_item")
        agent._send(r, "denied", {"qid": qid, "item": item, "reason": "unknown_item"})
        return
    n, fields = _shape(data)
    if not agent._send(r, "reply", {"qid": qid, "item": item, "projection": proj, "data": data}):
        agent._send(r, "denied", {"qid": qid, "item": item, "reason": "too_big"})
        agent.emit("denied", r=r, dir="out", ok=False, item=item, reason="too_big")
        return
    agent.emit("reply", r=r, dir="out", item=item, projection=proj, n=n, fields=fields)


def on_reply(agent, env) -> None:
    r = agent.rels.get(env.frm)
    b = env.body
    qid = str(b.get("qid", ""))
    q = agent.state["answers"].get(qid)
    if not q or q.get("cid") != r.contact_id:
        agent.emit("dropped", r=r, dir="in", ok=False, reason="replay", envelope_kind=env.kind)
        return
    q.update(status="answered", data=b.get("data"), projection=b.get("projection"))
    agent._save()
    n, fields = _shape(b.get("data"))
    agent.emit("reply", r=r, dir="in", item=q["item"], projection=str(b.get("projection", "")), n=n, fields=fields)


def on_denied(agent, env) -> None:
    r = agent.rels.get(env.frm)
    qid = str(env.body.get("qid", ""))
    q = agent.state["answers"].get(qid)
    if q and q.get("cid") == r.contact_id:
        q.update(status="denied", reason=str(env.body.get("reason", ""))[:32])
        agent._save()
    agent.emit("denied", r=r, dir="in", ok=False, item=str(env.body.get("item", ""))[:64],
               reason=str(env.body.get("reason", ""))[:32])


__all__ = ["on_query", "on_reply", "on_denied", "EnvelopeError"]
