"""A SURE «escalate» verdict routes the request to the errand portal before the model is trusted (V2-851 F5, CRIT-E27).

The brief's `escalate_or_inline` question is answered in the turn's one Jev trip. When it is SURE — at or above the
licence (`verdicts.LICENCE`), the verdict the declared task clauses produce (a document, a reply drafted from his mail)
— the one router decides: the request goes to the errand portal (`escalate_req` → the close's launch →
`acts/errand` → `flow_door` → `flow_of.route`), whether or not the model called `escalate_to_slowbrain`, and the
model's inline act or answer of that turn is NOT executed: no inline `reply`, no send. The turn's one line is the
start line the close already says for an escalation with no words («on it»).

Not a re-run after the stream: the verdict is read where the model's output is held anyway — at its first word
(`follow_up_pass.Hold`) and at each call it makes (`gate_calls`) — waiting for a brief in flight at most `wait_s()`.
Measured on battery C9 before this (2026-11-05): the verdict flipped to escalate at 0.52-0.62 and Flash still answered
inline, sending what should have waited. Read at the act floor (A7, K2); a call that LEAVES the machine is held from
the LICENCE by declared exception — holding a send sends nothing, and C9's band (0.52-0.62) straddles the floor.
"""
from __future__ import annotations

import os
import time

from loguru import logger

#: The calls a routed turn still lets through: the commission itself, and the model saying it could not read him.
PASS = frozenset({"escalate_to_slowbrain", "not_understood"})


def is_player(name: str) -> bool:
    """The call hands the request to one of OUR players (`acts/media.CARD_OF_TOOL`, the one declaration): it sends
    nothing outward, so a sure escalate has nothing to protect there (V2-860 T1.1)."""
    try:
        from nucleo.acts.media import CARD_OF_TOOL
        return str(name or "") in CARD_OF_TOOL
    except Exception as e:  # noqa: BLE001 — an unreadable declaration keeps the old routing
        logger.debug(f"route_by_verdict: players unreadable — {e!r}")
        return False

def stays_home(name: str, args) -> bool:
    """The call is one of OUR cards' declared acts that does not LEAVE the machine (`widgets.effects.leaves`): the
    card is the executor, and a sure escalate has nothing to protect there — the same reason a player call runs
    (V2-887). Measured on the kindergarten bench: «impórtame todos los contactos» with Contacts open and Google
    linked — the model called `contactos:sync_contacts`, the verdict said `escalate` and a worker was sent to do
    what one call does. A leaving act (a send) still routes: its consent lives in the task."""
    if name != "widget_data" or not isinstance(args, dict):
        return False
    try:
        from widgets import effects
        from nucleo.request import base
        wid, act = base(str(args.get("widget_id") or "")), str(args.get("action") or "")
        return bool(wid and act) and not effects.leaves(wid, act)
    except Exception as e:  # noqa: BLE001 — unreadable: the verdict routes, as before
        logger.debug(f"route_by_verdict: app act unreadable — {e!r}")
        return False


def wait_s() -> float:
    """How long the model's words and calls wait for a brief in flight before they run on their own."""
    try:
        return max(0.0, float(os.getenv("ZAELAR_ROUTE_WAIT_S", "1.5")))
    except ValueError:
        return 1.5


def player_ran(brief) -> str:
    """The player the model handed this turn to («» when none): its catalogue is the turn's answer, not an errand."""
    try:
        return str((brief or {}).get(_PLAYER_KEY) or "")
    except Exception as e:  # noqa: BLE001 — an unreadable brief reads as «no player»
        logger.debug(f"route_by_verdict: player unreadable — {e!r}")
        return ""


_PLAYER_KEY = "_player_ran"


def _mark(brief, name: str) -> None:
    try:
        if brief is not None:
            brief[_PLAYER_KEY] = name
    except Exception as e:  # noqa: BLE001 — an unmarkable brief only keeps the old routing
        logger.debug(f"route_by_verdict: player not marked — {e!r}")


def sure_escalate(brief, floor: float | None = None) -> bool:
    """The brief's escalate verdict is SURE (≥ `floor`, by default the act floor) — never waits, never raises."""
    try:
        from nucleo.turn import brief as _tb, verdicts as _v
        choice, info = _tb.read(brief, _tb.ESCALATE_KEY, "", min_confidence=_v.act_floor() if floor is None else floor)
        return bool(info) and bool(info.get("used", True)) and choice == "escalate"
    except Exception as e:  # noqa: BLE001
        logger.debug(f"route_by_verdict: unreadable verdict — {e!r}")
        return False


def ready(brief) -> bool:
    try:
        from nucleo import jev
        return bool(brief) and jev._is_ready(brief)
    except Exception:  # noqa: BLE001
        return True


def decided(brief, t0: float, wait: float):
    """True/False once the verdict can be read, None while the brief is in flight and the wait has not passed."""
    if brief and not ready(brief) and time.monotonic() - t0 < wait:
        return None
    return sure_escalate(brief)


def gate_calls(on_tool_call, *, brief, escalate_req: dict, operator_text: str, emit, t0: float, wait: float):
    """The model's calls through the verdict: under a sure «escalate» an inline call is not run and the request is
    the commission. A brief still in flight is waited for, at most what is left of `wait` since `t0`."""
    def _call(name, args):
        if brief:   # V2-887 step 8: a call was made — the doors it reaches ask their own questions, on their own
            from nucleo.turn import brief_doors   # thread, merged into the brief: how many acts his words asked, and
            brief_doors.fire(brief, "portal" if name == "escalate_to_slowbrain" else "" if name in PASS else "call")
        if name not in PASS and brief and not ready(brief):
            left = wait - (time.monotonic() - t0)
            if left > 0:
                try:
                    brief["event"].wait(left)
                except Exception as e:  # noqa: BLE001 — an unawaitable brief reads as in flight
                    logger.debug(f"route_by_verdict: brief not awaited — {e!r}")
        player = is_player(name) or stays_home(name, args)
        if player and not escalate_req.get("routed"):
            _mark(brief, name)               # its words are said and no errand opens behind it (V2-860 T1.1)
            return on_tool_call(name, args)
        from nucleo.turn import commission as _c, verdicts as _v   # a call that LEAVES is held from the licence
        if name not in PASS and sure_escalate(brief, _v.LICENCE if _c.leaves({"name": name, "args": args}) else None):
            _mark(brief, "")                 # a routed send after a player: the turn's words are the errand's
            escalate_req.setdefault("held_calls", []).append({"name": name, "args": dict(args or {})})   # V2-874
            route(escalate_req, operator_text, emit, why=f"call:{name}", brief=brief)
            return None
        return on_tool_call(name, args)
    return _call


def owns(escalate_req: dict | None) -> bool:
    """The request was routed by a sure verdict: it is the turn's commission, final — no later step of the close
    swaps it for a card act, a show or a picture search, or annuls it (battery C9: the third rung ran the messaging
    card's `reply` inline on a routed «answer that mail», and the consent his mail's taint asks for never came)."""
    return bool((escalate_req or {}).get("routed"))


def route(escalate_req: dict, operator_text: str, emit, *, why: str, brief=None, held: str = "") -> None:
    """The request is the turn's commission (the errand portal launches it at the close, through `flow_of.route`).
    The ONLY opener of an errand the model did not call (V2-857 phase 8: no word backstop): its event says the
    verdict, its confidence and where it was read (`source`: the model's call it held, or `verdict` at its words)."""
    first = not escalate_req.get("routed")
    if held:
        escalate_req["held_words"] = held   # V2-874: what the model wrote and the Hold kept unsaid (nothing called)
    escalate_req["routed"] = True
    from nucleo.turn import brief_doors   # V2-887 step 8: the request is a commission — the portal's questions fly now
    brief_doors.fire(brief, "portal")
    if escalate_req.get("v") is None:
        escalate_req["v"] = operator_text
    if first:
        from nucleo.turn import brief as _tb
        choice, info = _tb.read(brief, _tb.ESCALATE_KEY, "", min_confidence=0.0) if brief else ("", None)
        emit("brain", "🧭 sure escalate verdict — the request goes to its task, nothing runs inline", role="system",
             text=str(operator_text or "")[:160], extra={"cat": "flash", "why": why, "routed": True, "source": why,
                                                         "verdict": str(choice or ""),
                                                         "confidence": float((info or {}).get("confidence") or 0.0)})
        from nucleo.turn import commission   # V2-874: the one rule, in shadow beside what routing did
        commission.shadow(emit, at="route", brief=brief, escalate_req=escalate_req, text=operator_text)
