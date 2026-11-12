"""Does an inline tag LEAVE the machine? Read from what is declared, never from its name (V2-893 L2, CRIT-K2b):
`voice/tag_protocol.json` names each tag's OWNER — `app` leaves as the card's manifest declares the act (`app:<card>`:
that card's act of the tag's name), `connector:<id>` carries the effects its catalog declares (`tags`), `canvas` and
`engine` never leave, `call` crosses the call's own gate. Undeclared carries nothing (node 2.1737 keeps that set
empty); unreadable leaves — the cheap side holds it."""
import json
from functools import lru_cache
from pathlib import Path

from loguru import logger


@lru_cache(maxsize=1)
def owners() -> dict:
    return dict(json.loads((Path(__file__).parents[2] / "voice/tag_protocol.json").read_text("utf-8"))["owners"])


@lru_cache(maxsize=None)
def connector_tags(cid: str) -> dict:
    from connectors import catalog
    return dict(next((m for m in catalog.load_manifests() if m.get("id") == cid), {}).get("tags") or {})


def leaves(action="", extra=None, *_) -> bool:
    try:
        from widgets import effects
        action, x = str(action or ""), extra if isinstance(extra, dict) else {}
        kind, _sep, who = str(owners().get(action) or "").partition(":")
        data = x.get("data") if isinstance(x.get("data"), dict) else {}
        wid, act = (who, action.split(".", 1)[-1]) if who else (x.get("id"), data.get("action"))
        if kind == "app":
            return bool(wid and act) and effects.leaves(str(wid), str(act))
        return kind == "connector" and effects.EXTERNAL_SEND in (connector_tags(who).get(action) or ())
    except Exception as e:  # noqa: BLE001 — an unreadable declaration holds the tag, never sends it blind
        logger.debug(f"tag_effects: {action} unread — {e!r}")
        return True
