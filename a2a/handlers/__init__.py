"""Inbound dispatch: one handler per kind. The gate runs BEFORE anything is decrypted:

- `connect.request` is the only kind a stranger may send;
- `connect.accept` / `connect.decline` need our outgoing request;
- every other kind needs an accepted relationship — otherwise the envelope is dropped UNREAD (I2);
- unknown kinds, bad signatures, replays and expired envelopes are dropped with their reason (one `dropped` row,
  nothing from the envelope is kept).
"""
from __future__ import annotations

from ..envelope import KINDS, Envelope, EnvelopeError
from ..transport.base import Mail
from . import connect, live, messages, query

HANDLERS = {
    "connect.request": connect.on_request,
    "connect.accept": connect.on_accept,
    "connect.decline": connect.on_decline,
    "connect.revoke": connect.on_revoke,
    "msg.text": messages.on_text,
    "grant.notice": messages.on_grant_notice,
    "grant.revoked": messages.on_grant_revoked,
    "query": query.on_query,
    "reply": query.on_reply,
    "denied": query.on_denied,
    "live.offer": live.on_offer,
    "live.closed": live.on_closed,
}
assert set(HANDLERS) == set(KINDS), "every kind has exactly one handler"

_NEEDS = {"connect.request": None, "connect.accept": ("outgoing", "accepted"), "connect.decline": ("outgoing",)}


def dispatch(agent, mail: Mail) -> str:
    """→ the outcome: the kind handled, or `dropped:<reason>`."""
    wire = mail.body if isinstance(mail.body, dict) else {}
    kind = wire.get("kind", "")
    r = agent.rels.get(mail.from_did)

    def drop(reason: str) -> str:
        agent.emit("dropped", peer=mail.from_did, rel=r.rel if r else "", cid=r.contact_id if r else "",
                   dir="in", ok=False, reason=reason, envelope_kind=kind[:32])
        return f"dropped:{reason}"

    if kind not in HANDLERS:
        return drop("unknown_kind")
    need = _NEEDS.get(kind, ("accepted",))
    if need is not None and (r is None or r.status not in need):
        return drop("stranger")
    try:
        env = Envelope.open(agent.me, wire, from_did=mail.from_did, now=int(agent.clock()), seen=agent.rels.seen())
    except EnvelopeError as e:
        return drop(e.reason)
    agent.rels.mark_seen(env.id)
    HANDLERS[kind](agent, env)
    return kind
