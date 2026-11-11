"""nucleo/turn/card_act.py — same subject is not same errand: a card's act is the card's (V2-879 O1).

Measured in the lab sandbox (es, 2026-11-11): a coffee-shop search running, then «ponme esas cafeterías en el mapa».
`screen_action` is asked only while cards are open, so the owner rule had no card verdict for the CLOSED map; the
route said `steer` into the search and the one relay door sent his words to its worker («Voy a ello», no map). The
verdict that names a closed card is the catalogue's. Read here once, by the owner rule (`stop.card_owns_the_turn`,
which the relay door and the steer backstop read) and by the route (`flow_of.joins_as` → `card`). No word list:
three verdicts the brief already paid, and the manifests.
"""
from __future__ import annotations

from loguru import logger


def named(brief, *, surfaces_running=None) -> str:
    """The card the turn's paid verdicts give its one act to, "" when none. Never raises.

    An order to be DONE, not told (`wants_words=act` at the licence), whose one act (`acts_asked` not sure of several)
    the catalogue (`catalog_widget`, or `catalog_closed` with other cards open) gives to a card at VETO. Never: a card
    that declares itself a momentary process view (`transient` — the search banner is an errand's work); the card a
    running errand DELIVERS into (`surfaces.deliverable_card` — «open the best one» over an empty results sheet is a
    choice for its rows, V2-878 §5); any card while an errand that BUILDS a card runs (the card it builds is not
    named). `surfaces_running`: the live errands' surfaces (default: read from the dispatcher)."""
    try:
        from nucleo import surfaces
        from nucleo.turn import acts_asked, brief as _tb, verdicts as _v
        if brief is None or acts_asked.several(brief):
            return ""
        words, w_info = _tb.read(brief, _tb.WORDS_KEY, "", min_confidence=_v.LICENCE)
        if not w_info or words != "act":
            return ""
        running = set(_running_surfaces() if surfaces_running is None else surfaces_running or ())
        if surfaces.WIDGET in running:
            return ""
        from widgets import runtime
        delivered_into = {surfaces.deliverable_card(str(s or "")) for s in running}
        for key in (_tb.CATALOG_KEY, _tb.CATALOG_CLOSED_KEY):
            card, info = _tb.read(brief, key, "", min_confidence=_v.VETO)
            base = str(card or "").split("::", 1)[0].strip().lower()
            if (info and base and base != "none" and base not in delivered_into
                    and not (runtime.get(base) or {}).get("transient")):
                return base
    except Exception as e:  # noqa: BLE001 — unreadable: no card claims the turn, today's path stands
        logger.debug(f"card_act: unreadable — {e!r}")
    return ""


def joins(flow: dict, brief) -> bool:
    """Does a request that resembles `flow` join it as a CARD's act instead? Not when the turn's paid stop verdict ends
    the errand (an order about the errand itself), nor for an errand that builds a card or the act on its own sheet."""
    from nucleo import surfaces
    from nucleo.request import stop as _stop
    own = str(flow.get("surface") or "")
    if _stop.ends(_stop.verdict(brief)) or own == surfaces.WIDGET:
        return False
    card = named(brief)
    return bool(card) and card != surfaces.deliverable_card(own)


def _running_surfaces() -> list[str]:
    from nucleo import dispatch
    return [str(e.get("surface") or "") for e in (dispatch.pending_summaries() or [])]
