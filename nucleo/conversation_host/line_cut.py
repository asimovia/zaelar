"""A line he sends enters the conversation whole up to the manager's `line_max_chars` — past it, cut OUT LOUD (INI-078).

Both doors of a line (a typed one, `entry.typed`; a device's own ear, `controls.local_phrase`) pass through here.
"""
from __future__ import annotations

import asyncio
import uuid


def clipped(text: str, dev: str = "") -> str:
    """His line as it enters the conversation: whole up to the manager's `line_max_chars`. Past it the rest is cut, and
    the cut is SAID — an alert, and a line to him with how much was read — never a silent truncation."""
    t = str(text or "").strip()
    from conversation.config import Config
    cap = Config.line_max_chars          # the manager's own threshold; read here without building a session's config
    if len(t) <= cap:
        return t
    from voice import observer
    observer.emit("alert", "a line he sent was cut", text=t[:200], extra={"chars": len(t), "kept": cap, "device": dev})
    from nucleo.conversation_host.words import PackWords
    line = PackWords().line("line_cut", near=t[:400])
    if line:
        from nucleo.pulse import notices
        said = notices.notify("zaelar", line.format(kept=cap, chars=len(t)), key=f"conv:cut:{uuid.uuid4().hex[:8]}")
        try:
            asyncio.get_running_loop().create_task(said)
        except RuntimeError:
            asyncio.run(said)
    return t[:cap]
