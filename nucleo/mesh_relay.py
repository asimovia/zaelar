"""nucleo/mesh_relay.py — a priced skill of a mesh agent, reached through the deployment's relay (mediated egress).

The rule of `mesh_agents` is «free agents only; a 402 is reported and never paid». A deployment with mediated egress
(`nucleo/energy/egress.py`) adds exactly ONE way past it, and it is not the engine paying: the relay may hold a
client credential of its own with an agent, and then a priced skill of that agent is served under that credential.
The engine still never pays, never holds the credential and never names an agent:

  · the call goes to `<egress>/p/mesh/<agent host><skill path>` with this process's own egress credential. Which
    agents the relay covers, and with which credential, is the relay's business; an agent it does not cover is
    answered there (`404`/`503`), never forwarded;
  · it is only attempted when this deployment can PRICE the skill — a row of the tariff family `agent`
    (`nucleo/energy/tariffs.py`), keyed `<agent_id>.<skill_id>`. A priced skill whose cost could not be put on the
    account is not called at all: what the deployment cannot charge, it does not spend;
  · its cost is charged when the work it bought ENDS (`mesh_jobs`), at the cost the agent measured when it reports
    one, else at that tariff row.

Self-host: no mediated egress, so `route()` answers "direct" for a free skill and "refused" for a priced one —
byte-identical to the free-only rule.
"""
from __future__ import annotations

import urllib.parse

from loguru import logger

DIRECT, RELAY, REFUSED = "direct", "relay", "refused"
TARIFF_FAMILY = "agent"


def _note(e: BaseException) -> None:
    import sys
    logger.debug(f"mesh_relay: {sys._getframe(1).f_code.co_name} — {type(e).__name__}: {e}")


def tariff_key(agent_id: str, skill_id: str) -> str:
    """The tariff row a priced skill is charged by: `<agent_id>.<skill_id>`, lower-case."""
    return f"{str(agent_id or '').strip()}.{str(skill_id or '').strip()}".lower()


def priced(agent_id: str, skill_id: str) -> bool:
    """Does this deployment hold a price for this skill? Pure read of the cached tariff table; never the network."""
    try:
        from nucleo.energy import tariffs
        return tariffs.has_rate(TARIFF_FAMILY, tariff_key(agent_id, skill_id))
    except Exception as e:  # noqa: BLE001 — an unreadable table prices nothing, and nothing priced is called
        _note(e)
        return False


def available() -> bool:
    """Does this deployment route through mediated egress with a credential to present?"""
    try:
        from nucleo.energy import egress
        return egress.mediated() and bool(egress.credential())
    except Exception as e:  # noqa: BLE001
        _note(e)
        return False


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
    """The lease gate, asked BEFORE a priced call starts (the same door every paid model call crosses)."""
    try:
        from nucleo.energy import lease_gate
        return lease_gate.check("agent")
    except Exception as e:  # noqa: BLE001 — no gate readable: refuse; a priced call is not the direction to fail open
        _note(e)
        return False
