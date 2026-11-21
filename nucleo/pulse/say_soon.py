"""A door's line from code that does not await (an errand refused, a row's question): the out-of-turn mouth
(`notices.notify`) scheduled on the running loop, with the door's notice `key` — deduped, owed if he is away."""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("zaelar.notices")

_SOON: set = set()             # lines handed to the loop, held so the loop does not collect them


def notify_soon(text: str, *, key: str, title: str = "zaelar", **voice_kw) -> bool:
    """`notices.notify` on the running loop. False when there is nothing to say or no loop (a test, the boot): the
    door's own record keeps it."""
    text = (text or "").strip()
    if not text:
        return False
    from nucleo.pulse import notices
    try:
        task = asyncio.get_running_loop().create_task(notices.notify(title or "zaelar", text, key=key, **voice_kw))
    except RuntimeError:
        logger.debug(f"notices: no loop for an out-of-turn line — {text[:80]}")
        return False
    _SOON.add(task)
    task.add_done_callback(_SOON.discard)
    return True
