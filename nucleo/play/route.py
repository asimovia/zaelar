"""nucleo/play/route.py — where a request goes: the conversation, the programme, or a worker.

One ordered list, first match wins. Its inputs are what the turn already has: the declared actions the request
names, whether it asks for several, and whether its reading is a sure errand (work outside one declared action).

    1. ONE declared action, not several:
         its class declares the worker (`classify` is `escalate`)         → ERRAND
         it leaves the machine and the reading is a sure errand           → ERRAND
         otherwise                                                        → PLAY
    2. a sure errand reading, several actions, or two different actions   → ERRAND
    3. nothing declared is named                                          → TALK

An action that stays on the machine needs no worker even under an errand reading — its widget is the executor — while
a leaving one follows the reading. That is today's router (`nucleo.turn.route_by_verdict.stays_home`), kept: the test
compares both over every declared action.
"""
from __future__ import annotations

TALK, PLAY, ERRAND = "talk", "play", "errand"


def _declared(acts) -> list[tuple[str, str]]:
    from . import programme
    out = []
    for wid, action in acts or ():
        if programme.of(wid, action) is not None:
            out.append((str(wid).split("::", 1)[0].strip().lower(), str(action).strip()))
    return out


def destination(acts=(), *, several: bool = False, errand: bool = False) -> str:
    """`acts` = the (widget, action) pairs the request names; `several` = it asks for more than one action;
    `errand` = its reading is a sure errand (work outside one declared action)."""
    from widgets import actions, runtime
    from . import programme
    named = set(_declared(acts))
    if len(named) == 1 and not several:
        wid, action = next(iter(named))
        spec = ((runtime.get(wid) or {}).get("actions") or {}).get(action) or {}
        if actions.classify(spec, action) == actions.ESCALATE:
            return ERRAND
        if errand and programme.of(wid, action)["leaves"]:
            return ERRAND
        return PLAY
    if errand or several or len(named) > 1:
        return ERRAND
    return TALK
