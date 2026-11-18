"""A Brain Worker that reaches a MESSAGE act hands it to the send's owner: a worker never sends a message itself.

A worker on a larger errand («find a table and send it to her») may end in a message. That message is the owner's
like any other (`owner.intake`, the act's fields as the hint): the owner asks him once by voice, sends on his yes and
says the receipt's line. The worker is told it was handed over and goes on with the rest of its errand.
"""
from __future__ import annotations

from loguru import logger

#: What the worker reads back: the message is no longer its own.
HANDED = ("The message is now with the assistant's message owner: it asks the operator once by voice, sends it on "
          "his yes and tells him the result. Do NOT send it again and do not ask him about it; go on with the rest "
          "of your task, or finish.")


async def hand(rec, action: str, payload: dict | None) -> dict | None:
    """The bridge's answer when `action` is a message act (handed over), else None (the act goes on its way)."""
    if action != "widget_data":
        return None
    try:
        from nucleo import on_his_behalf
        from nucleo.send import turn
        wid, act, inner = on_his_behalf._resolve(payload or {})
        if not turn.owned(wid, act, inner):
            return None
        from nucleo.workers import exit_gate
        if exit_gate.under_mandate(rec, "message", str(inner.get("channel") or inner.get("platform") or "")):
            for k in ("contact_id", "chat_id"):   # ids chosen by the owner only: the worker names people by name
                inner.pop(k, None)
            return None                          # an errand's standing mandate covers it: the worker's own act
        from nucleo.send import owner
        said = str(getattr(rec, "heard", "") or getattr(rec, "request", "") or "")
        line = await owner.intake(said, {**dict(inner), "_act": act}, by="worker")
        if line:
            from nucleo.send import draft, receipt
            await receipt.say_out(line, f"send:worker:{getattr(draft.current(), 'id', '') or abs(hash(line))}")
        return {"ok": True, "result": {"handed": True, "note": HANDED}}
    except Exception as e:  # noqa: BLE001 — a message that could not be handed over is refused, never sent around it
        logger.warning(f"send.worker: a message act was not handed over — {e!r}")
        return {"ok": False, "error": "the message could not be handed to the assistant's message owner"}
