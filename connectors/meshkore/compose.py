"""connectors/meshkore/compose.py — a peer's turn on a cluster, composed by the connector itself (R-2, E7d-3).

A cluster is the connector's conversation with another agent, not his: it has its own composer, in three steps.

  1. SYSTEM — who it is on the network and its hard rules (untrusted channel, concise, which language goes where):
     language data (`i18n/genesis/<lang>/voice.json › meshkore.cluster_system`), never prose here. Identity-safe by
     construction: nothing of the operator's memory or screen is read.
  2. MESSAGE — what the bridge composed (`bridge/turn.py`: the relationship's capsule, its pact and rhythm, the peer's
     text, the security trailer LAST); taken as it comes.
  3. CALL — ONE call through the model client with its relay (`provider_chain`), no stream, bounded in time.

Its only act is the one its permission grants: starting an errand with the permission's bounded context, through the
one errand door (`acts.errand.escalate_to_slowbrain`), offered with the conversation manager's declared `start_task`
schema. The reply is made sayable (`voice/reply_text.sanitize_reply`) and goes back to the bridge, which applies its
outbound guard and its `[[cluster.*]]` tags as always. With the conversation manager on, the turn enters it as an
EVENT of origin `cluster.msg` and runs there, after his words (`events_in.run_as_event`).
"""
from __future__ import annotations

import asyncio
import os

from loguru import logger

#: the event topic a peer's turn enters the conversation manager as
ORIGIN = "cluster.msg"
#: what a permission names the bounded errand by (`perms.gated_tool_names`)
_ERRAND = "escalate_to_slowbrain"


def system() -> str:
    """The cluster's system, in the operator's language pack, with the agent's name and his language in it."""
    from i18n import langs
    from nucleo.self import snapshot
    spec = langs.current_language()
    tpl = str(langs.words("meshkore.cluster_system", default="") or "")
    return tpl.replace("{name}", snapshot.name()).replace("{op_lang}", str(getattr(spec, "native", "") or spec.code))


def tools(tool_names) -> list[dict]:
    """The acts this turn may take: the declared `start_task`, only when the cluster's permission grants errands."""
    if _ERRAND not in set(tool_names or ()):
        return []
    from nucleo.conversation_host import acts
    spec = next(t for t in acts.catalog() if t.name == "start_task")
    params = {"type": "object", "required": ["request"],
              "properties": {"request": spec.schema["properties"]["request"]}}
    return [{"type": "function", "function": {"name": spec.name, "description": spec.about, "parameters": params}}]


def _on_tool_call(escalate_ctx):
    def call(name: str, args: dict) -> None:
        if name != "start_task":
            return
        request = str((args or {}).get("request") or "").strip()
        if request:
            from nucleo.acts import errand
            errand.escalate_to_slowbrain(request, context=dict(escalate_ctx or {}))   # never the operator's trust
    return call


async def _complete(text: str, tier: dict, tool_names, escalate_ctx) -> str:
    from nucleo.llm import provider_chain
    from nucleo.llm.fast_client import FastClient
    from voice import reply_text
    offered = tools(tool_names)
    out = await FastClient().complete([{"role": "system", "content": system()}, {"role": "user", "content": text}],
                                      spec=provider_chain.spec_for(tier),
                                      max_tokens=int(os.getenv("MESHKORE_MAX_TOKENS", "220")),
                                      tools=offered or None, on_tool_call=_on_tool_call(escalate_ctx) if offered else None)
    return reply_text.sanitize_reply(out).strip()


async def respond(text: str, *, tool_names=None, escalate_ctx=None, timeout: float | None = None) -> str:
    """One peer turn, relayed once to the next provider when the first fails by the provider's fault."""
    from nucleo.llm import provider_chain
    cap = timeout or float(os.getenv("MESHKORE_TIMEOUT", "120"))
    tier = provider_chain.pick()
    if not tier:
        raise RuntimeError("MeshKore: no cluster brain provider with a credential")
    try:
        return await asyncio.wait_for(_complete(text, tier, tool_names, escalate_ctx), timeout=cap)
    except Exception as e:  # noqa: BLE001 — classified; with a relay, THIS turn is tried again once
        nxt = provider_chain.note_failure(str(e), tier=tier)
        if not nxt:
            raise
        logger.warning(f"MeshKore: relay «{tier['name']}» → «{nxt['name']}» mid-turn, trying again")
        return await asyncio.wait_for(_complete(text, nxt, tool_names, escalate_ctx), timeout=cap)


async def turn(text: str, *, tool_names=None, escalate_ctx=None) -> str:
    """The bridge's brain: the peer's turn as an event of the conversation manager when it is on, else here."""
    from nucleo.conversation_host import events_in
    return await events_in.run_as_event(
        ORIGIN, text[:2000], lambda: respond(text, tool_names=tool_names, escalate_ctx=escalate_ctx))
