"""The card's answers in his language: one door to the UI pack (`widgets.mensajeria.<key>`), never a literal (V2-880)."""
from __future__ import annotations

import logging


def say(key: str, default: str, **kw) -> str:
    try:
        from i18n import runtime as _rt
        text = _rt.text(f"widgets.mensajeria.{key}", default)
    except Exception as e:  # noqa: BLE001 — no language table: the English default stands
        logging.getLogger("zaelar.mensajeria.words").info(f"mensajeria: i18n unreadable ({e})")
        text = default
    for k, v in kw.items():
        text = text.replace("{" + k + "}", str(v))
    return text
