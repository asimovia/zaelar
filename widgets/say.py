"""An app's answer in his language: one door to the UI pack (`widgets.<app>.<key>`), the English default when the pack
has none. A sentence written as a literal in an app's code reaches every speaker in one language (V2-877 #10)."""
from __future__ import annotations

import logging


def say(app: str, key: str, default: str, **kw) -> str:
    try:
        from i18n import runtime as _rt
        text = _rt.text(f"widgets.{app}.{key}", default)
    except Exception as e:  # noqa: BLE001 — no language table: the English default stands
        logging.getLogger("zaelar.widgets.say").info(f"{app}: i18n unreadable ({e})")
        text = default
    for k, v in kw.items():
        text = text.replace("{" + k + "}", str(v))
    return text
