"""live.offer / live.closed: the envelope only TELLS the recipient a share exists; the samples go through the live
ring (MK-10), never through the mailbox."""
from __future__ import annotations


def on_offer(agent, env) -> None:
    r = agent.rels.get(env.frm)
    b = env.body
    sid = str(b.get("share_id", ""))[:64]
    if not sid:
        agent.emit("dropped", r=r, dir="in", ok=False, reason="malformed", envelope_kind=env.kind)
        return
    agent.state["in_shares"][sid] = {"did": r.did, "cid": r.contact_id, "item": str(b.get("item", ""))[:64],
                                     "schema": str(b.get("schema", ""))[:64],
                                     "expires_at": float(b.get("expires_at", 0) or 0), "cursor": 0, "closed": False}
    agent._save()
    agent.emit("live_open", r=r, dir="in", item=str(b.get("item", ""))[:64], share=sid[:8], ttl_s=0)


def on_closed(agent, env) -> None:
    r = agent.rels.get(env.frm)
    sid = str(env.body.get("share_id", ""))[:64]
    sh = agent.state["in_shares"].get(sid)
    if sh and sh["did"] == r.did:
        sh["closed"] = True
        agent._save()
    agent.emit("live_close", r=r, dir="in", share=sid[:8])
