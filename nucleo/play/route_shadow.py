"""nucleo/play/route_shadow.py — where each turn's request SHOULD go, recorded beside where it went (stage `shadow`).

At the close of a turn the facts are all there: the calls the model made, the turn's readings (how many acts he asked,
a sure errand, an order, a canvas verb), the declared actions its doors ran and whether an errand was launched. From
the first three `route.destination` says conversation, programme or worker; the last two say what the path did. One
`play/route` event carries both. It is a `route_drift` when they differ, and when a sure order that names no canvas
verb ended with no declared action run, no errand, no row opened at its close and no question asked — by a door or
in its own words — the turn did something else and nothing serves what he ordered.

Records only: nothing here changes a turn, and nothing raises into one.
"""
from __future__ import annotations

from loguru import logger

from . import programme as _programme
from . import route as _route
from . import switch as _switch


def _named(calls, brief) -> list[tuple[str, str]]:
    """The declared actions the turn's own readings name: the model's card calls, and the brief's target."""
    from nucleo.request import base
    out: list[tuple[str, str]] = []
    for c in calls or ():
        args = c.get("args") if isinstance(c, dict) else None
        if isinstance(c, dict) and c.get("name") == "widget_data" and isinstance(args, dict):
            out.append((base(args.get("widget_id")), str(args.get("action") or "")))
    from nucleo.flash import direct_action
    target = direct_action.from_brief(brief)
    if target[0]:
        out.append((base(target[0]), str(target[1])))
    return [p for p in dict.fromkeys(out) if _programme.of(*p) is not None]


def _ran(ops) -> list[tuple[str, str]]:
    """The declared actions the turn's doors ran (its data-ops)."""
    from nucleo.request import base
    out = [(base(w), str(a)) for w, a in ops or ()]
    return [p for p in dict.fromkeys(out) if _programme.of(*p) is not None]


def _sure_order(brief) -> bool:
    """A sure order that owes an act (not words) and names no canvas verb."""
    from nucleo.acts import canvas_verdict
    from nucleo.turn import brief as tb, verdicts
    kind, info = verdicts.read(brief, tb.REQUEST_KEY, None, min_confidence=verdicts.VETO)
    if not info or str(kind or "") != "order":
        return False
    words, w_info = verdicts.read(brief, tb.WORDS_KEY, None)
    if w_info and str(words or "") == "tell":
        return False
    return canvas_verdict.sure_no_canvas(brief)


def read(*, brief, calls, ops, escalated: bool, acted_elsewhere: bool, asked: bool) -> dict:
    """The record of one turn: `{dest, legacy, agree, unserved, named, ran}`. Pure over its readings."""
    from nucleo.turn import acts_asked, route_by_verdict
    named, ran = _named(calls, brief), _ran(ops)
    errand = route_by_verdict.sure_escalate(brief) or any(
        isinstance(c, dict) and c.get("name") == "escalate_to_slowbrain" for c in calls or ())
    dest = _route.destination(named, several=acts_asked.several(brief), errand=errand)
    if escalated:                       # a send is an errand too: its worker task (V2-931)
        legacy = _route.ERRAND
    elif ran:
        legacy = _route.PLAY
    else:
        legacy = _route.TALK
    unserved = (legacy == _route.TALK and not acted_elsewhere and not asked and _sure_order(brief))
    return {"dest": dest, "legacy": legacy, "agree": dest == legacy, "unserved": unserved,
            "named": [f"{w}:{a}" for w, a in named], "ran": [f"{w}:{a}" for w, a in ran]}


def closed(*, brief, calls, ops, escalate_req, acted_elsewhere: bool, opened: bool = False, said: str = "",
           emit=None) -> dict | None:
    """The turn closed: record where its request should go and where it went. None with the stage off."""
    try:
        if not _switch.stage("shadow"):
            return None
        from nucleo.request import ends_asking
        from nucleo.turn import reply
        rec = read(brief=brief, calls=calls, ops=ops, escalated=(escalate_req or {}).get("v") is not None,
                   acted_elsewhere=bool(acted_elsewhere),
                   asked=bool(opened) or reply.asked() or ends_asking(said))
        from voice import observer
        drift = not rec["agree"] or rec["unserved"]
        observer.emit("play", "route_drift" if drift else "route", role="system",
                      text=f"{rec['dest']} · path: {rec['legacy']}" + (" · the order is unserved" if rec["unserved"] else ""),
                      extra={"cat": "system", **rec})
        return rec
    except Exception as e:  # noqa: BLE001 — a record that could not be written never touches the turn
        logger.debug(f"play/route_shadow: turn not recorded — {e!r}")
        return None
