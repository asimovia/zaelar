"""nucleo/acts/wall_tab.py — an order to OPEN a tab of the wall that the name resolver names with certainty (V2-761).

Neutral ground for both channels, like `presence.py`: the voice lane (`voice/engine/llm/providers/fast_lane.py`)
and the probe mirror (`probe_actionmap.try_fast_lanes`) read the SAME verdict, so they cannot drift.

Why a lane and not the model. Measured on the live engine with the operator's own six phrases for the widget
catalogue («enséñame el catálogo de aplicaciones», «o los widgets, ábreme esa lista»…), three rounds each, with a
clean window per phrase: the model called `show_panel` 10-13 times out of 18. The rest it refused («no tengo un
catálogo como tal»), promised with no tool, or — worst — spent a background worker «listing his custom widgets»,
which the tab he named already shows. The same phrase, a different decision each time.

What decides here is not a phrase table. It is the NAME: `widgets.runtime.identify`, the resolver that opens every
card by its name or alias, says the utterance names a system surface that is a tab of the wall — with no widget
matched and no tie — and the utterance is an order to open/show (`looks_like_show_strict`, the grammar the show
backstop already reads, which excludes create and close). The aliases are data (`system_surfaces`), so a new tab,
or a new word for this one, is a data edit. For the catalogue the name alone is enough (see the function); the chat
still needs an order.
"""
from __future__ import annotations

from loguru import logger


def named_wall_tab(text: str) -> str:
    """The wall tab (`apps`, `apps-custom`, `chat`) this utterance asks for, or "" — fail-closed.

    The name resolver names the tab, and an unnegated open/show order asks for it — every tab alike. V2-903 a6
    (phone, 14:38): the catalogue used to open on its NAME alone, and «…o los widgets en pantalla», a cut tail of a
    close sentence, opened the wall. A noun is not an order; a question with no open verb («¿qué widgets tengo?»)
    goes to the action map's seeds (ES+EN, the custom tab included) or to the model's `show_panel`."""
    try:
        from nucleo.flash import router_guards as _rg
        from nucleo.flash.negation import unnegated_match
        if _rg.looks_like_create_widget(text) or _rg.looks_like_close(text):
            return ""
        from widgets import runtime as _rt
        res = _rt.identify(text) or {}
        if res.get("match") or res.get("ambiguous"):
            return ""
        from nucleo.turn.prompt.catalogs import wall_tab_for
        tab = wall_tab_for(res.get("system"), text)
        # «No me abras el chat» carries the verb and names the tab; the clause arithmetic both promise gates
        # already share says the verb is negated.
        ordered = _rg.looks_like_show_strict(text) and unnegated_match(_rg._SHOW_STRICT_RE, _rg._norm_txt(text))
        return tab if (tab and ordered) else ""
    except Exception:  # noqa: BLE001 — a lane that cannot decide leaves the turn to the model
        return ""


def open_named_panel(text: str, emit, *, proposed: bool, card: str, acted: dict, _router, _tool_fired,
                     operator_text: str = "") -> bool:
    """A promised show that names the CONNECTORS surface and no card opens that panel, on the connector he named.

    connect-email-by-voice (V2-834 T14): «ábreme el panel de conectores con el correo» was promised with no tool, and
    the promise backstop — which knew only canvas cards — opened the MESSAGING card its «correo» named. `conectores` is
    a declared system surface (`widgets/system_surfaces.py` + its JS mirror), so `identify` names it. The panel opens
    through THE door every `show_panel` goes through (`tool_executor_calls._t_show_panel`: canon tab and action, the
    connector by the router, `_tool_fired`, the act of UI) — never a second emitter of the same event, which drifts
    from the first (V2-252; S1 audit H6)."""
    if not proposed or card:
        return False                       # nothing promised, or a card named: the show backstop owns it
    try:
        from widgets import runtime as _rt
        res = _rt.identify(text) or {}
        if res.get("match") or res.get("ambiguous") or res.get("system") != "conectores":
            return False
        from nucleo.flash import tool_executor_calls as _calls
        fired = "show_panel" in _tool_fired
        _calls._t_show_panel(args={"panel": "conectores", "action": "open", "connector": text}, _router=_router,
                             _tool_fired=_tool_fired, acted=acted, emit=emit, operator_text=operator_text or text,
                             text=text)
        return not fired
    except Exception as e:  # noqa: BLE001 — a backstop that cannot decide leaves the turn as it was
        logger.debug(f"wall_tab: the named panel was not opened — {e!r}")
        return False
