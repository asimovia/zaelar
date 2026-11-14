"""connect.request / accept / decline / revoke."""
from __future__ import annotations

from .. import events
from ..grants import contact_audience


def on_request(agent, env) -> None:
    b = env.body
    r, outcome = agent.rels.incoming(env.frm, rel=str(b.get("rel", ""))[:16], name=str(b.get("name", ""))[:80],
                                     matched_by=str(b.get("matched_by", ""))[:16], note=str(b.get("note", ""))[:280])
    if outcome in ("rate_limited", "held", "duplicate"):
        agent.emit("dropped", r=r, dir="in", ok=False, reason="rate_limited" if outcome != "duplicate" else "replay",
                   envelope_kind=env.kind)
        return
    crossing = outcome == "crossing"
    agent.emit("request", r=r, dir="in", matched_by=r.matched_by, crossing=crossing, excerpt=r.note)
    if crossing:                                           # both asked: accepted without a second card
        agent._on_accepted(r, crossing=True)
        r = agent.rels.get(r.did)
        agent._send(r, "connect.accept", {"rel": r.rel, "name": agent.display_name})
        agent.emit("accept", r=r, dir="out", crossing=True, scopes=["messages"])
        return
    answer = agent.asker({"type": "request", "peer": r.did[8:16], "rel": r.rel, "name": r.name,
                          "note": events.excerpt(r.note), "matched_by": r.matched_by})
    agent.emit("request_card", r=r, dir="in", answer=str(answer) if answer else "pending")
    if answer == "accept":
        agent.accept(r.did)
    elif answer == "decline":
        agent.decline(r.did)


def on_accept(agent, env) -> None:
    r = agent.rels.get(env.frm)
    was = r.status
    r = agent.rels.accepted_by_peer(env.frm)
    if was != "accepted":
        agent._on_accepted(r)
        r = agent.rels.get(r.did)
    agent.emit("accept", r=r, dir="in", crossing=was == "accepted", scopes=["messages"])


def on_decline(agent, env) -> None:
    r = agent.rels.declined_by_peer(env.frm)
    agent.emit("decline", r=r, dir="in", declined_until=0)


def on_revoke(agent, env) -> None:
    r = agent.rels.get(env.frm)
    agent.grants.revoke_all(contact_audience(r.contact_id))
    for sid, sh in list(agent.state["in_shares"].items()):
        if sh["did"] == r.did:
            sh["closed"] = True
    agent._save()
    r = agent.rels.revoke(env.frm)
    agent.emit("disconnect", r=r, dir="in")
