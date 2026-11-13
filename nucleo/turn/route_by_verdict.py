"""A SURE «escalate» verdict routes the request to the errand portal before the model is trusted (V2-851 F5, CRIT-E27).

The brief's `escalate_or_inline` question is answered in the turn's one Jev trip. When it is SURE — at or above the
licence (`verdicts.LICENCE`), the verdict the declared task clauses produce (a document, a reply drafted from his mail)
— the one router decides: the request goes to the errand portal (`escalate_req` → the close's launch →
`acts/errand` → `flow_door` → `flow_of.route`), whether or not the model called `escalate_to_slowbrain`, and the
model's inline act or answer of that turn is NOT executed: no inline `reply`, no send. The turn's one line is the
start line the close already says for an escalation with no words («on it»).

Not a re-run after the stream: the verdict is read where the model's output is held anyway — at its first word
(`follow_up_pass.Hold`) and at each call it makes (`Turn.gate`) — for a brief in flight, until it lands or the stream ends.
Measured on battery C9 before this (2026-11-05): the verdict flipped to escalate at 0.52-0.62 and Flash still answered
inline, sending what should have waited. Read at the act floor (A7, K2); a call that LEAVES the machine is held from
the LICENCE by declared exception — holding a send sends nothing, and C9's band (0.52-0.62) straddles the floor.

The words follow the act (CRIT-K2b corollary): ONE `Turn` releases the calls, the words and the inline tags on one state;
in flight or in the band the calls decide, so the words and tags wait with them until the stream ends (V2-893 L2).
"""
from __future__ import annotations

import asyncio
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


def in_band(brief) -> bool:   # sure at the licence, not at the act floor: only a call that LEAVES routes (C9)
    from nucleo.turn import verdicts as _v
    return sure_escalate(brief, _v.LICENCE) and not sure_escalate(brief)


def decided(brief):
    """True/False once the verdict is final; None in flight or in the band, where the calls decide (K2b R1)."""
    return None if (brief and not ready(brief)) or in_band(brief) else sure_escalate(brief)


def _leaves(name, args) -> bool:
    from nucleo.turn import commission
    return commission.leaves({"name": name, "args": args})


def _sends(item) -> bool:   # a queued call by its card's effects, a tag by what the grammar declares
    from nucleo.flash import tag_effects
    return _leaves(*item[2]) if item[0] == "call" else tag_effects.leaves(*item[2])


class Turn:
    """ONE routing decision: the model's calls (`gate`), words (`words`, `settle`: the Hold) and tags (`tags`) on one
    state — routed, inline, or not yet; what waits runs in the order it was written as soon as the verdict lands."""

    def __init__(self, brief, escalate_req=None, operator_text: str = "", emit=None, t0=None, wait: float = 0.0):
        self.brief, self.req, self.text = brief, {} if escalate_req is None else escalate_req, operator_text
        self.emit = emit or (lambda *a, **k: None)
        self.t0, self.wait, self.settled, self.queue, self.cut = t0 or time.monotonic(), wait, False, [], False

    def routed(self) -> bool:
        return owns(self.req) or sure_escalate(self.brief)

    def words(self):
        w = True if owns(self.req) else decided(self.brief)
        if w is not None and self.queue and not self.settled:
            self._flush()                    # the verdict landed: what waited runs now, in order
        return w

    def gate(self, on_tool_call):
        def _call(name, args):
            if self.cut:
                return None                  # a cut stream's late calls (the `finally` after a barge-in) never run
            if self.brief:   # V2-887 step 8: a call was made — the doors it reaches ask their own questions, on their
                from nucleo.turn import brief_doors   # own thread, merged into the brief: how many acts his words asked
                brief_doors.fire(self.brief, "portal" if name == "escalate_to_slowbrain" else "" if name in PASS else "call")
            self.words()
            if name not in PASS and not self.settled and (self.queue or (self.brief and not ready(self.brief))):
                self.queue.append(("call", on_tool_call, (name, dict(args or {})), {}))   # never awaited here
                return None
            return self._decide(name, args, on_tool_call)
        return _call

    def _decide(self, name, args, on_tool_call):
        if (is_player(name) or stays_home(name, args)) and not owns(self.req):
            _mark(self.brief, name)          # its words are said and no errand opens behind it (V2-860 T1.1)
            return on_tool_call(name, args)
        from nucleo.turn import verdicts as _v   # a call that LEAVES is held from the licence
        if name not in PASS and sure_escalate(self.brief, _v.LICENCE if _leaves(name, args) else None):
            _mark(self.brief, "")            # a routed send after a player: the turn's words are the errand's
            self.req.setdefault("held_calls", []).append({"name": name, "args": dict(args or {})})   # V2-874
            route(self.req, self.text, self.emit, why=f"call:{name}", brief=self.brief)
            return None
        return on_tool_call(name, args)

    def tags(self, tag_emit):
        """None runs on a routed turn; until the state is final they wait in the queue with the calls."""
        def _emit(*a, **k):
            if self.cut or self.routed():
                return None
            if not self.settled and self.words() is None:   # a final state ran what waited first (`words`)
                return self.queue.append(("tag", tag_emit, a, k))
            return tag_emit(*a, **k)
        return _emit

    def _flush(self) -> None:
        from nucleo.turn import verdicts as _v
        queue, self.queue = self.queue, []
        if any(_sends(x) for x in queue) and sure_escalate(self.brief, _v.LICENCE):   # one send held routes them all
            for _kind, _run, a, _k in (x for x in queue if x[0] == "tag" and _sends(x)):   # a tag as the call it is
                self.req.setdefault("held_calls", []).append({"name": str(a[0]), "args": dict((a + ({},))[1] or {})})
            route(self.req, self.text, self.emit, why="held:" + str(next(x for x in queue if _sends(x))[2][0]), brief=self.brief)
        for kind, run, a, k in queue:        # then in the order the model wrote them
            if kind == "call":
                self._decide(*a, run)
            elif not self.routed():
                run(*a, **k)

    async def settle(self) -> bool:
        """The stream ended: the brief is awaited off the loop (Jev's own timeout when what waits leaves), then what
        waited runs in order. True when routed. A brief that never came is no verdict: a call runs into its task."""
        if not self.settled:
            from nucleo import jev
            leaving = any(_sends(x) for x in self.queue)
            left = (max(self.wait, jev._timeout_s()) if leaving else self.wait) - (time.monotonic() - self.t0)
            if left > 0 and self.brief and not ready(self.brief):
                try:
                    await asyncio.to_thread(self.brief["event"].wait, left)
                except Exception as e:  # noqa: BLE001 — an unawaitable brief reads as in flight: no verdict
                    logger.debug(f"route_by_verdict: brief not awaited — {e!r}")
            self.settled = True
            self._flush()
        return self.routed()


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
