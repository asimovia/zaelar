"""nucleo/flash/held_send.py — his explicit order over a row he has SEEN is the confirmation (V2-800).

The operator's rule, for every act that reaches the real world: «una orden explícita de mandarlo sobre un borrador
que ya ha visto ES la confirmación». Asking again — in the chat and on the card — after he has read the draft and
said «send it» is the double question he reported, and a second question is exactly what made the next «yes»
answer the wrong thing.

Generic by construction. A widget whose action delivers a row held for his word (a draft, a prepared booking, a
staged payment) exposes `held_row(action, payload) -> dict | None` in its data module, returning the row only when
he has already had it in front of him. The turn's verdict must surely name that very act (`undecided.sure_order`,
the operator's `consent.intent_act_at`). Then the ONE consent rule decides with `his_yes=True`
(`nucleo/consent.decide`): his standing «ask» rule, a missing fact, a doubt and the radius rail still stop.
Both channels and the leave gate read `confirmed()` — one reader, so they can never disagree.
"""
from __future__ import annotations

import importlib
import logging

logger = logging.getLogger("zaelar.held_send")


def held(widget_id: str, action: str, payload) -> dict | None:
    """The row this call would deliver, when the widget declares one he has seen — else None. Never raises."""
    wid = str(widget_id or "").split("::", 1)[0].strip().lower()
    if not wid or not action:
        return None
    try:
        hook = getattr(importlib.import_module(f"widgets.{wid}.data"), "held_row", None)
        row = hook(action, dict(payload or {})) if callable(hook) else None
        return row if isinstance(row, dict) and row else None
    except Exception as e:  # noqa: BLE001 — an unreadable hook keeps the friction it had
        logger.info(f"held_send: {wid}.held_row unreadable ({e}) — the act keeps its question")
        return None


def ordered(widget_id: str, action: str, payload, brief) -> bool:
    """A seen held row AND a verdict sure of this very act: his order is the yes, if the consent rule agrees."""
    if brief is None or held(widget_id, action, payload) is None:
        return False
    from nucleo.flash import undecided as _und
    return _und.sure_order(brief, widget_id, action)


def confirmed(widget_id: str, action: str, payload, brief) -> bool:
    """`ordered`, and the one consent rule runs it with `his_yes` — the reader every gate asks."""
    if not ordered(widget_id, action, payload, brief):
        return False
    try:
        from nucleo import consent
        from nucleo.flash import frontend as _fe
        return not consent.asks(_fe.action_verdict(widget_id, action, payload, his_yes=True))
    except Exception as e:  # noqa: BLE001
        logger.info(f"held_send: consent unreadable ({e}) — the act keeps its question")
        return False
