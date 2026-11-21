"""The flows that are open, and whether a request is one of them said AGAIN.

Not a routing: the list of what is open (`candidates`) and the one cheap identity a door may still ask — is this
request the SAME one as an open flow's (`lexical`: the containment yardstick, microseconds, no model)? The listing door
uses it so a search asked twice re-runs into its own sheet instead of minting a second box (`join`); the card gate uses
it to find a pending question the same request already has.
"""
from __future__ import annotations

from loguru import logger


def candidates() -> list[dict]:
    """Every open flow a request can be: live workers, errands parked on a question, escalations and fast passes in
    flight, one that just ended, and a fast pass that just delivered. Same entry shape as `named_errand.known()`, plus
    `delivered`."""
    from nucleo.errands import named as _ne
    out = list(_ne.known(with_finished=True))
    try:
        from nucleo.matching import same_errand
        from nucleo.workers import ended as _ended
        for d in _ended.recent_listing_deliveries():
            goal = str(d.get("goal") or "")
            if goal and d.get("sheet") and not any(same_errand(goal, str(e.get("request") or "")) for e in out):
                out.append({"id": f"delivered:{d.get('id')}", "request": goal, "sheet": str(d["sheet"]),
                            "delivered": True, "parked": False})
    except Exception as e:  # noqa: BLE001 — a reader never breaks a turn
        logger.debug(f"open_flows: deliveries unreadable — {type(e).__name__}: {e}")
    return [c for c in out if str(c.get("request") or "").strip()]


def lexical(text: str, pool: list[dict]) -> dict | None:
    """The open flow whose request `text` IS (containment both ways), or None."""
    from nucleo.matching import same_errand
    return next((c for c in pool if same_errand(text, str(c.get("request") or ""))), None)
