"""Which card his words NAME and which card is in front of him NOW — read from his words and the screen, never from
the verdict. Split by concern out of `nucleo/acts/canvas_verdict.py` (2026-11-09) so the canvas door stays the door;
`nucleo/flash/direct_action.py` re-exports these names, as before."""
from __future__ import annotations



def named_cards(operator_text: str) -> list[str]:
    """Every card his words NAME (alias or name, never context): «the calendar and the messages» is two, and so is
    «cierra la agenda y los mensajes», whose second card is called by its catalogue NAME (sandbox 2026-10-29 C6)."""
    try:
        from widgets import naming as _naming, runtime as _rt
        if (res := _rt.identify(operator_text or "") or {}).get("by_context"):
            return []
        cands = res.get("candidates") or []
        top = max((float(c.get("score") or 0) for c in cands), default=0.0)
        out = [str(res["match"])] if res.get("match") else [
            str(c["id"]) for c in cands if top > 0 and float(c.get("score") or 0) == top] if res.get("ambiguous") else []
        return out + [str(c["id"]) for c in cands if str(c["id"]) not in out and _naming.says_the_name(operator_text, c["id"])]
    except Exception:  # noqa: BLE001
        return []


def _open_now() -> list[str]:
    try:
        from server.voice_api import open_instances
        return [str(i) for i in open_instances() if str(i)]
    except Exception:  # noqa: BLE001
        return []


def catalogue_names(widget_id: str) -> list[str]:
    from widgets import naming as _naming
    return _naming.catalogue_names(_base(widget_id))


def _says_the_name(operator_text: str, widget_id: str) -> bool:
    from widgets import naming as _naming
    return _naming.says_the_name(operator_text, _base(widget_id))


def on_screen_now(widget_id: str) -> bool:
    """Whether the card is in front of him NOW — open by the canvas report, or brought by THIS turn. The report
    comes from the browser and lags the turn that presents a card: full17 M1 «show me the chart» opened it and the
    answer said «I can't pull up the chart itself here» over it, because the report still said closed."""
    base = str(widget_id or "").split("::", 1)[0].strip().lower()
    try:
        from nucleo.flash import canvas_visibility as _cvis
        if _cvis.is_open(base):
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        from nucleo import canvas_focus as _cf
        return base in _cf.this_turn_cards()
    except Exception:  # noqa: BLE001
        return False


def _base(widget_id: str) -> str:
    from nucleo.flash import direct_action as _da   # lazy: direct_action re-exports this module's names
    return _da._base_of(widget_id)
