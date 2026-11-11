"""nucleo/circuit/card_call.py — the call as the card will STORE it, read before an end state is rendered (V2-886).

Split from `spec.py` (its file ceiling): one reader of the cards' `spec_call` seam.
"""
from __future__ import annotations

from loguru import logger


def card_call(wid: str, action: str, payload: dict | None) -> tuple[str, dict]:
    """The call as the CARD will store it (V2-886 fila 5): its data module may declare `spec_call(action, payload) →
    (action, payload)` — the action whose end state this call owes (a routed act) and its values normalised the way
    the row keeps them («jueves» → the date, «8 pm» → 20:00). Measured 2026-11-11: an end state rendered from his raw
    words was compared with the normalised row, so a move that landed was judged unmet and said back as a failure.
    No hook, or an unreadable one: the call as given."""
    try:
        import importlib
        base = str(wid or "").split("::", 1)[0].strip().lower()
        hook = getattr(importlib.import_module(f"widgets.{base}.data"), "spec_call", None)
        if callable(hook):
            a, p = hook(str(action or ""), dict(payload or {}))
            return str(a or action), dict(p or {})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"spec: {wid}.spec_call unreadable ({e!r}) — the call's own values stand")
    return str(action or ""), dict(payload or {})
