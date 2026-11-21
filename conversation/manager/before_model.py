"""His words before any model (plan F2 §3, V2-942): a phrase the host knows VERBATIM (`Shortcut`) runs its act, then
something of his that is OPEN takes them by the host's doors (`Route`); the line the door answers is said and the run
ends with that door as its origin. Split out of `run.py`, which calls it first thing in a run."""
from __future__ import annotations

from typing import TYPE_CHECKING

from conversation import guard
from conversation.inbox.mailbox import Batch

if TYPE_CHECKING:
    from conversation.manager.loop import Conversation, Running


async def taken(conv: "Conversation", r: "Running", batch: Batch, content: list) -> bool:
    """Before any model, his words go first to a phrase the host knows VERBATIM (`Shortcut`, its act run, V2-942),
    then to something of his that is OPEN by the host's doors (plan F2 §3): the line that door answers is said, and the
    run ends with that door as its origin. No hit, nobody took them, or the doors failed or were late: the model
    answers, as always."""
    text = " ".join(str(getattr(e.body, "text", "") or "").strip() for e in content).strip()
    if not text:
        return False
    for origin, door in (("actionmap", conv.shortcut), ("routed", conv.route)):
        if door is None:
            continue
        try:
            line = await guard.call(conv.em, conv.cfg, "tools", door.take(conv.account, text), conv.cfg.tool_ms,
                                    {"run": r.run_id})
        except Exception as e:  # noqa: BLE001 — a door that fails never silences him: the next one, or the model
            r.said.append((origin, f"{type(e).__name__}"))
            continue
        if line is None:
            continue
        from conversation.manager import run
        run._emit(conv, "command", r, command=origin, said=bool(line))
        if line:
            await run._publish(conv, r, batch, str(line), 0)
        else:
            run._silent(conv, r, origin, conv.clock.now_ms())
        return True
    return False


async def door(conv: "Conversation", r: "Running", batch: Batch, steps: int, stream) -> None:
    """An act's door answered him in its own words (its result `says: door`): that line, as is, ends the run —
    the model is asked nothing more, and the calls of the same answer it therefore never ran are named."""
    from conversation.manager import run
    from conversation.ports import ToolCall
    run._emit(conv, "command", r, command=run.DOOR)
    r.origin = run.DOOR
    await run._publish(conv, r, batch, r.door_line, steps)
    if skipped := [e.name async for e in stream if isinstance(e, ToolCall)]:
        run._emit(conv, "command", r, command="door_skipped", tools=skipped)
