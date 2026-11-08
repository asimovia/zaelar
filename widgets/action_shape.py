"""widgets/action_shape.py — a refused data-op hands back the action's DECLARED shape (V2-860 T2.7, CRIT-K44).

Measured in watch-a-video-not-listen-to-it__us: `youtube.set_volume {}` was refused as `bad_level` and the refusal
reached nobody who could act on it. Manifest payloads are prose (`{"level": "0-100"}`), not a schema, so nothing can
coerce a call; the refusal is what carries level 2 of the action. Called by `server_api.brain_action`, the one door
Flash, the card and a worker share.
"""
from __future__ import annotations

from loguru import logger


def on_refusal(wid: str, action: str, payload, res):
    """A refused data-op carries the action's DECLARED payload (`payload`) and, when the refusal names no field, the
    first declared key the call left out (`field`) — level 2 of the card's action, handed over only on a refusal, so
    the caller's next call can carry the shape (V2-860 T2.7: `set_volume {}` was refused as `bad_level` and nobody
    could act on it). Read through `act_policy.declared_actions` (re-exported by `nucleo.flash.frontend`), the one reader."""
    if not (isinstance(res, dict) and (res.get("error") or res.get("ok") is False)):
        return res
    try:
        from nucleo.flash.frontend import declared_actions     # act_policy's reader, its public re-export
        decl = (declared_actions(wid).get(action) or {}).get("payload")
    except Exception as e:  # noqa: BLE001 — an unreadable declaration leaves the refusal as the card wrote it
        logger.debug(f"brain_action: {wid}:{action} declaration unread — {e!r}")
        return res
    if not isinstance(decl, dict) or not decl:
        return res
    out = {**res, "payload": decl}
    missing = [k for k in decl if k not in (payload if isinstance(payload, dict) else {})]
    if not out.get("field") and missing:
        out["field"] = missing[0]
    return out
