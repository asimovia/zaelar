"""What a card is called in his language — the one reader every line that names a card goes through, so a reply
never says a widget's id («youtube», «agenda») where he reads its name («YouTube», «Calendar»)."""
from __future__ import annotations

from loguru import logger


def _base(card: str) -> str:
    return str(card or "").split("::", 1)[0].strip().lower()


def card_name(card: str, code: str = "") -> str:
    """The card's name in the language `code` (default: his), else its manifest name, else a native surface's own
    name (Settings, a phone page, INI-042 #47), else its id."""
    base = _base(card)
    try:
        from i18n import runtime as _i18n_rt
        name = str(_i18n_rt.text(f"widgets.{base}.name", "", code=code or None) or "")
        if name:
            return name
    except Exception as e:  # noqa: BLE001
        logger.debug(f"names: bundle name unread — {e}")
    try:
        from widgets import runtime as _rt
        if name := str((_rt.get(base) or {}).get("name") or ""):
            return name
    except Exception as e:  # noqa: BLE001
        logger.debug(f"names: widget name unread — {e}")
    try:
        from i18n import runtime as _i18n_rt
        for key in (f"surfaces.{base}.name", f"mobile.{base}"):
            if name := str(_i18n_rt.text(key, "", code=code or None) or ""):
                return name
    except Exception as e:  # noqa: BLE001
        logger.debug(f"names: surface name unread — {e}")
    return base
