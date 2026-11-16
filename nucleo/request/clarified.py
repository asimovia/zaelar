"""nucleo/request/clarified.py — our clarifying question is answered by the act his answer ran: its row closes.

Measured: «crea un grupo» → «¿un grupo de contactos o de mensajería?» kept a row waiting; his answer ran the group on
another row, and the first stayed `waiting` for ever. A question row of ours that retains his UTTERANCE (no act of
its own, `ask_outside_door.held`) about either card the act touched is closed when that act runs.
"""
from __future__ import annotations

from loguru import logger


def answered(*cards: str) -> int:
    """Close the open utterance questions about any of `cards`; how many were closed. Never raises."""
    try:
        from nucleo import circuit
        from nucleo.circuit import asker
        from nucleo.cli import worker_api
        from nucleo.request import base, inline_ask
        want = {base(c) for c in cards if c}
        n = 0
        for a in worker_api.open_asks():
            ret = (asker.artefact(str(a["task_id"])) or {}).get("retained") or {}
            if ret.get("kind") != inline_ask.UTTERANCE or base(ret.get("widget")) not in want:
                continue
            if inline_ask.take(str(a.get("ask_id") or "")):
                circuit.settle(row=str(a["task_id"]), state="done", outcome="answered: his answer ran the act")
                n += 1
        return n
    except Exception as e:  # noqa: BLE001 — a question that stays open is a row he can still answer
        logger.debug(f"clarified: open questions unread ({e!r})")
        return 0
