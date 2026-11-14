"""a2a — your agent reaches your friends' agents (V2-866).

One door: `A2AAgent` (agent.py). Builders: `from_network()` for the real MeshKore network, `FakeNetwork` for the lab.
Separate code (I8): this package imports from connectors/meshkore only the key loader in `identity.engine_default`,
and nothing outside imports a2a except through this module.
"""
from __future__ import annotations

from .agent import A2AAgent
from .events import attach_bus
from .grants import Grant, contact_audience
from .identity import Identity
from .items import Item, ItemRegistry, declare_manifest, default_items
from .jobs import Jobs
from .server_api import WAKE_PATH, WakeGate, status_allowed
from .transport.fake import FakeNetwork


def from_network(me: Identity | None = None, base: str | None = None, **kw) -> A2AAgent:
    """An agent on the real network (`A2A_API_BASE`, default api.meshkore.com)."""
    from .discovery import HttpDirectory
    from .transport.http import SignedHttp
    from .transport.live import HttpLive
    from .transport.mailbox import HttpMailbox
    me = me or Identity.engine_default()
    http = SignedHttp(me, base=base)
    return A2AAgent(me, HttpMailbox(http), HttpDirectory(http), HttpLive(http), **kw)


_RUNTIME: dict = {"agent": None, "jobs": None}


def set_runtime(agent=None, jobs=None) -> None:
    """The engine registers the running agent here (or clears it), so the turn and the widgets reach it through this
    module only — no layer above imports the server."""
    _RUNTIME.update(agent=agent, jobs=jobs)


def runtime():
    """The running agent, or None while A2A is off."""
    return _RUNTIME["agent"]


def runtime_jobs():
    return _RUNTIME["jobs"]


def accepted() -> list:
    """The accepted relationships of the running agent ([] while off) — the state gate of the turn's A2A tools."""
    agent = _RUNTIME["agent"]
    if agent is None:
        return []
    try:
        return [r for r in agent.rels.all() if r.status == "accepted"]
    except Exception:                                       # noqa: BLE001 — an unreadable store offers nothing
        return []


def contact_block(cid: str) -> dict | None:
    """The `a2a` block of a contact record: `{did, status, grants, since}` (did = 8 chars), None if no relationship."""
    agent = _RUNTIME["agent"]
    if agent is None or not cid:
        return None
    try:
        r = agent.rels.by_contact(str(cid))
        if r is None:
            return None
        grants = [{"item": g.item, "verbs": list(g.verbs), "expires_at": g.expires_at}
                  for g in agent.grants.for_audience(contact_audience(r.contact_id))]
        from .identity import short
        return {"did": short(r.did), "status": r.status, "grants": grants, "since": r.since}
    except Exception:                                       # noqa: BLE001
        return None


__all__ = ["contact_block", "accepted", "declare_manifest", "runtime", "runtime_jobs", "set_runtime", "A2AAgent", "FakeNetwork", "Grant", "Identity", "Item", "ItemRegistry", "Jobs", "WAKE_PATH", "WakeGate",
           "attach_bus", "contact_audience", "default_items", "from_network", "status_allowed"]
