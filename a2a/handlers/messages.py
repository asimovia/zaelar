"""msg.text and the grant notices. A message is DATA (I1): stored with trust="contact", handed to `on_message` as a
card, never to a prompt."""
from __future__ import annotations

INBOX_MAX = 500


def on_text(agent, env) -> None:
    r = agent.rels.get(env.frm)
    text = str(env.body.get("text", ""))[:4000]
    if not agent.grants.allowed(r.contact_id, "messages", "append").allowed:
        agent.emit("denied", r=r, dir="in", ok=False, item="messages", reason="no_row")
        return
    row = {"id": env.id, "rel": r.rel, "cid": r.contact_id, "name": r.name, "ts": env.ts, "text": text,
           "trust": "contact"}
    inbox = agent.state["inbox"]
    inbox.append(row)
    del inbox[:-INBOX_MAX]
    agent._save()
    agent.rels.touch_in(r.did)
    shown = "card"
    if agent.on_message:
        try:
            agent.on_message(dict(row))
        except Exception:
            shown = "stored"
    agent.emit("msg", r=r, dir="in", len=len(text), shown=shown, excerpt=text)


def on_grant_notice(agent, env) -> None:
    r = agent.rels.get(env.frm)
    item = str(env.body.get("item", ""))[:64]
    entry = {"item": item, "verbs": list(env.body.get("verbs", []))[:5],
             "expires_at": float(env.body.get("expires_at", 0) or 0)}
    agent.state["shared_with_me"].setdefault(r.contact_id, {})[item] = entry
    agent._save()
    agent.emit("grant_notice", r=r, dir="in", item=item, verbs=entry["verbs"], expires_at=entry["expires_at"])


def on_grant_revoked(agent, env) -> None:
    r = agent.rels.get(env.frm)
    item = str(env.body.get("item", ""))[:64]
    agent.state["shared_with_me"].get(r.contact_id, {}).pop(item, None)
    agent._save()
    agent.emit("revoke", r=r, dir="in", item=item, audience="contact")
