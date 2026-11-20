#
# MeshKore channel brain = the connector's own composer in UNTRUSTED profile (E7d-3; before, the old FlashBrain's).
#
# This module does NOT reason: it hands the peer's turn to `connectors/meshkore/compose.py` (identity-safe system as
# language data, one relayed call, only the errand its permission grants).
#
# Wiring seam: `make_brain()` (called by server lifespan) returns an `async brain(text, on_chunk=None) -> str`, so
# the bridge/connector remain brain-agnostic.
#
# Security: the peer has no tools surface but the errand its permission grants (`compose.tools`), the system never
# touches operator memory/PII, and the bridge appends the security trailer at the end of the turn.
#
# RELAY (2026-08-03): the tier is NO LONGER fixed once at boot — `nucleo.llm.provider_chain.pick()` is queried ON
# EACH turn (cheap: an in-memory cooldown dict, not a network call) and, if the turn fails because of the provider
# (quota/credential — see `provider_chain.classify_failure`), it relays and RETRIES that same turn once before
# giving up. Before: a Z.AI 429 killed the turn and the next heartbeat repeated the SAME broken call — no relay, no
# warning (diagnosed with the operator 2026-08-03: `bridge.py` heartbeat kept trying to answer a peer while Z.AI
# returned endless 429s, in a loop).
from loguru import logger


def _spec():
    """`ModelSpec` for the CURRENT chain tier (compat: used by `bridge.py`'s V2-075 evaluator, which only needs SOME
    reasonable spec to judge the conversation — it does not participate in `_brain` relay)."""
    from nucleo.llm import provider_chain
    tier = provider_chain.pick()
    if not tier:
        raise RuntimeError("MeshKore: ningún proveedor de cerebro de cluster con credencial disponible")
    return provider_chain.spec_for(tier)


def make_brain():
    """The channel brain: the connector's own composer (`compose.turn`, E7d-3), relayed per turn by its provider chain."""
    from connectors.meshkore import compose
    from nucleo.llm import provider_chain
    chain_now = provider_chain.chain()
    logger.info("MeshKore: channel composed by its own composer (untrusted profile) · chain: "
                + (" → ".join(t["name"] for t in chain_now) if chain_now else "(no credential configured)"))

    async def _brain(text: str, on_chunk=None, *, tool_names=None, escalate_ctx=None) -> str:
        out = await compose.turn(text, tool_names=tool_names, escalate_ctx=escalate_ctx)
        if on_chunk and out:
            on_chunk(out)
        return out

    return _brain
