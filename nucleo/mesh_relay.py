"""nucleo/mesh_relay.py — a priced skill of a mesh agent, reached through the deployment's relay (mediated egress).

The rule of `mesh_agents` is «free agents only; a 402 is never paid». A deployment with mediated egress
(`nucleo/energy/egress.py`) adds ONE way past it, and it is not the engine paying: the relay may hold a client
credential of its own with an agent. The engine still never pays, never holds that credential and never names an agent:

  · the call goes to `<egress>/p/mesh/<agent host><skill path>` with this process's own egress credential; which agents
    the relay covers, how and at what cost it books them, is the relay's business (it answers what it does not cover);
  · it is only attempted when this deployment can PRICE the skill — a row of the tariff family `agent`, keyed
    `<agent_id>.<skill_id>`: what the deployment cannot charge, it does not spend.

Self-host: no mediated egress, so a priced skill is refused — byte-identical to the free-only rule.
"""
from __future__ import annotations

import urllib.parse

DIRECT, RELAY, REFUSED = "direct", "relay", "refused"
TARIFF_FAMILY = "agent"


def tariff_key(agent_id: str, skill_id: str) -> str:
    """The tariff row a priced skill is charged by: `<agent_id>.<skill_id>`, lower-case."""
    return f"{str(agent_id or '').strip()}.{str(skill_id or '').strip()}".lower()


def priced(agent_id: str, skill_id: str) -> bool:
    """Does this deployment hold a price for this skill? Pure read of the cached tariff table; never the network."""
    from nucleo.energy import tariffs
    return tariffs.has_rate(TARIFF_FAMILY, tariff_key(agent_id, skill_id))


def available() -> bool:
    """Does this deployment route through mediated egress with a credential to present?"""
    from nucleo.energy import egress
    return egress.mediated() and bool(egress.credential())


def route(agent_id: str, skill_id: str, free: bool) -> tuple[str, str]:
    """How a call to this skill may go: `(DIRECT|RELAY|REFUSED, why)`. Free → direct, always. Priced → the relay,
    when this deployment has one AND a price for it; otherwise refused, with the reason said in one line."""
    if free:
        return DIRECT, ""
    if not available():
        return REFUSED, f"«{agent_id}» charges for «{skill_id}» and this engine only uses free skills — nothing was called"
    if not priced(agent_id, skill_id):
        return REFUSED, (f"«{agent_id}» charges for «{skill_id}» and this account has no price for it, so it cannot be "
                         f"charged — nothing was called")
    return RELAY, ""


def url(endpoint: str, path: str) -> tuple[str, str]:
    """`(url, bearer)` of a relayed call: `<egress>/p/mesh/<host><path>` and this process's egress credential."""
    from nucleo.energy import egress
    host = urllib.parse.urlsplit(endpoint).netloc
    return f"{egress.root()}/p/mesh/{host}{path}", egress.credential()


def admit() -> bool:
    """The lease gate, asked BEFORE a priced call starts (the same door every paid model call crosses; never raises)."""
    from nucleo.energy import lease_gate
    return lease_gate.check("agent")
