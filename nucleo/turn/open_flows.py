"""The flows that are open, and whether a request is one of them said AGAIN.

Whose his words are is decided once, at the turn's gate, before the model (`nucleo/switchboard`). What is left here is
not a second routing: it is the list of what is open (`candidates`) and the one cheap identity a door may still ask —
is this request the SAME one as an open flow's (`lexical`: the containment yardstick, microseconds, no model)? The
listing door uses it so a search asked twice re-runs into its own sheet instead of minting a second box (`join`).
"""
from __future__ import annotations

from loguru import logger


def candidates() -> list[dict]:
    """Every open flow a request can be: live workers, errands parked on a question, escalations and fast passes in
    flight, one that just ended, and a fast pass that just delivered. Same entry shape as `named_errand.known()`, plus
    `delivered`."""
    from nucleo.turn import named_errand as _ne
    out = list(_ne.known(with_finished=True))
    try:
        from nucleo.turn.errands_of_a_turn import same_errand
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
    from nucleo.turn.errands_of_a_turn import same_errand
    return next((c for c in pool if same_errand(text, str(c.get("request") or ""))), None)


async def join(text: str) -> dict:
    """The listing door: `{flow, sheet}` when this request is an open flow's said again and that flow has a sheet (the
    pass re-runs into it); `{}` for a new flow. A flow that is parked on his yes, ended or delivered is never joined by
    likeness: that is a new request, and the dispatcher's own continuity reads it. Never raises."""
    try:
        from nucleo import sheets as _sheets
        from nucleo.acts.errand import whole_request
        words = whole_request(text)
        hit = lexical(words, candidates()) if str(words or "").strip() else None
        if hit is None or hit.get("parked") or hit.get("ended") or hit.get("delivered"):
            return {}
        sheet = str(_sheets.sheet_of_flow(hit) or "")
        return {"flow": str(hit["id"]), "sheet": sheet} if sheet else {}
    except Exception as e:  # noqa: BLE001
        logger.debug(f"open_flows: the listing's flow unread, a new one — {type(e).__name__}: {e}")
        return {}


def a_discarded_turn(req: str, ctx: dict) -> bool:
    """A turn the ear threw away starts nothing: the chain that replaced it carries the request. Whose his words are
    was decided at the gate (`nucleo/switchboard`): the portal routes nothing a second time. Never raises."""
    try:
        from voice import trace as _trace
        from nucleo.turn import turn_marks
        t = _trace.current()
        if not t or ctx.get("kind") == "dev" or any(ctx.get(k) for k in ("task_uid", "born_uid", "confirmed", "replaces",
                                                                         "not_mine_of")):
            return False
        if not turn_marks.was_discarded(t):
            return False
        from voice.observer import emit
        emit("flow", "🧵 a discarded turn starts nothing — its chain carries the request", role="system", text=req[:160],
             extra={"cat": "flash", "as": "discarded"})
        return True
    except Exception as e:  # noqa: BLE001 — unreadable: the errand opens
        logger.debug(f"open_flows: the turn's mark unread — {e!r}")
        return False
