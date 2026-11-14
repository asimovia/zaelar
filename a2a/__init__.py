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
from .items import Item, ItemRegistry, default_items
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


__all__ = ["A2AAgent", "FakeNetwork", "Grant", "Identity", "Item", "ItemRegistry", "Jobs", "WAKE_PATH", "WakeGate",
           "attach_bus", "contact_audience", "default_items", "from_network", "status_allowed"]
