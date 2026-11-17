"""The rung that runs Claude itself, for a task that must (V2-931: a send is owned end to end by an Anthropic model).

Split out of `providers/__init__.py`: the chain there relays between rungs by health; a task marked for Claude takes
THIS rung or does not start — it is never relayed to another model.
"""
from __future__ import annotations

from loguru import logger

from nucleo.workers import providers as _p

#: The env mark a worker spec carries when its task must run on Claude itself (V2-931: a send is owned end to end by
#: an Anthropic model). `claude_start` reads it and takes `tier()` instead of the chain's first rung.
ANTHROPIC_MARK = "ZAELAR_WORKER_TIER"


def tier() -> dict | None:
    """The rung that runs Claude itself: the subscription rung where its credential resolves and it is not parked,
    else — on a desktop — the local licence the `claude` CLI is logged in with, on the table's Claude model. None in a
    container with no subscription rung (no browser login exists there): the caller says so instead of relaying to
    another model."""
    for t in _p.chain():
        if t.get("auth") == "oauth" and _p._store.available(t["name"]):
            return t
    if _p._is_container():
        return None
    lead = next((dict(k) for k in _p.KNOWN if k.get("lead")), None) or {}
    try:
        from config import models as _tabla
        lead = lead or dict(_tabla.lead("brain_worker") or {})
    except Exception as e:  # noqa: BLE001 — no table: the CLI's own default model on the licence
        logger.debug(f"providers: the model table's Claude rung unread — {e!r}")
    t = dict(_p.LICENSE_TIER)
    t["model"] = str(lead.get("model") or "")
    if lead.get("fast_model"):
        t["fast_model"] = lead["fast_model"]
    t["vision"] = True
    return t


def env_for(t: dict | None) -> dict:
    """`env_for_worker` for a given rung: the licence (no base URL) needs nothing but its model slots."""
    if not t:
        return {}
    if not t.get("base_url"):
        return {**_p.slot_env(t), **_p.vision_env(t)}
    tok = _p._credential(t)
    if not tok:
        return {}
    from nucleo.energy import egress as llm_egress
    if t.get("auth") == "oauth" and not llm_egress.mediated():
        return {"CLAUDE_CODE_OAUTH_TOKEN": tok, "CLAUDE_CODE_MAX_RETRIES": "3", **_p.slot_env(t), **_p.vision_env(t)}
    base, tok = llm_egress.route_url(t["base_url"], tok)
    return {"ANTHROPIC_BASE_URL": base, "ANTHROPIC_AUTH_TOKEN": tok, "CLAUDE_CODE_MAX_RETRIES": "3",
            **_p.slot_env(t), **_p.vision_env(t)}


def route(session, env: dict) -> str:
    """Point one spawn at Claude itself: the session learns its rung and `env` gets what it needs. Returns "" when
    routed, else why this task cannot start (said by the caller — it is never relayed to another model)."""
    session._tier = tier()
    if session._tier is None:
        return ("no Claude rung is available for this task (no subscription token and no local `claude` login in a "
                "container)")
    env.update(env_for(session._tier))
    if not session._tier.get("base_url"):
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("ANTHROPIC_AUTH_TOKEN", None)
    return ""
