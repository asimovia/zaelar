"""A queued message, followed to the connector's own receipt: the ONE final line he hears is the receipt's.

«Sent» when the order's outbox row says so, «could not be sent: why» when it fails; with neither inside `RECEIPT_S`,
once «not confirmed yet», and he is told when it lands, up to `LATE_S`.
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger

WIDGET = "mensajeria"
#: How long the receipt is waited for before he is told it is not confirmed yet, and the last look after that.
RECEIPT_S, LATE_S, POLL_S = 30.0, 600.0, 1.0


def _note(e: Exception) -> None:
    logger.debug(f"send.receipt: {type(e).__name__}: {e}")


def _owner_emit(label: str, d, **extra) -> None:
    from nucleo.send.owner import _emit
    _emit(label, d, **extra)


async def _say(d, key: str, **fmt) -> None:
    try:
        from nucleo.pulse import notices
        from nucleo.send import ask
        line = await ask.line(key, who=d.target.get("name"), **fmt)
        if line:
            await notices.notify("zaelar", line, key=f"send:{d.id}:{key}", kind="info")
    except Exception as e:  # noqa: BLE001
        _note(e)


async def follow(d, *, receipt_s: float = RECEIPT_S, late_s: float = LATE_S, poll_s: float = POLL_S) -> str:
    """Wait for the connector's own receipt of the queued order and say the ONE final line from it."""
    from nucleo.request import send_receipt
    t0, told_late = time.monotonic(), False
    while True:
        state, why = send_receipt.receipt(WIDGET, d.ref, None)
        if state == "sent":
            _owner_emit("sent", d)
            await _say(d, "send_done")
            return "sent"
        if state == "failed":
            _owner_emit("failed", d, why=why)
            await _say(d, "send_failed", why=why or "unknown")
            return "failed"
        waited = time.monotonic() - t0
        if waited >= late_s:
            _owner_emit("unconfirmed", d)
            return "unconfirmed"
        if waited >= receipt_s and not told_late:
            told_late = True
            await _say(d, "send_unconfirmed")
        await asyncio.sleep(poll_s)


tasks: set = set()


def follow_soon(d) -> None:
    try:
        t = asyncio.get_running_loop().create_task(follow(d))
        tasks.add(t)
        t.add_done_callback(tasks.discard)
    except RuntimeError as e:
        _note(e)
