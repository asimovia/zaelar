"""The `Route` port (INI-078 F2 steps 3-4, plan §3): his words to something of his that is OPEN reach it by the doors
that already decide it, before the model is called — in their own order:

  1. an open message draft: the send owner reads the sentence against it (`nucleo.send.owner.take`): who, what it says,
     send it, drop it — taken, its line is said; anything else is not his and goes on;
  2. a process in course or a row waiting on his answer: the switchboard (`nucleo.switchboard.route.take`) — «is this
     for process N, or for none?» — his stop to one of them ending its row through the one cancel door.

With nothing open it answers at once and costs nothing. The doors do not speak by themselves: the line they would say
is collected and handed back for the manager's mouth. They run on the engine's loop, where the processes live.

The words of the batch in course are kept (`said`): the send act hands them to the owner with the model's call, which
reads HIS words and takes the call's fields only for what they leave empty.
"""
from __future__ import annotations

_last = {"said": ""}


def said() -> str:
    """His words in the batch the manager is answering now (one batch at a time per account)."""
    return _last["said"]


class HostRoute:
    async def take(self, account: str, text: str) -> str | None:
        from nucleo.conversation_host.acts import _on_engine_loop
        from nucleo.send import draft, owner
        from nucleo.switchboard import board, route
        _last["said"] = text
        if draft.current() is not None:
            took, line = await _on_engine_loop(owner.take(text))
            if took:
                return line or ""
        if not board.open_processes():          # nothing open: nobody to take his words, no decision paid
            return None
        lines: list[str] = []
        from voice.observer import emit
        took = await _on_engine_loop(route.take(text, brain=None, emit=emit, say=lines.append))
        return (lines[-1] if lines else "") if took else None


async def send(args: dict, act: str = "") -> "object":
    """The model's message call — or a widget's message act (`act`, with its payload) — handed to the send owner with
    his words: the owner's line (always a question until his yes) is what the reply says. Nothing leaves here."""
    from conversation.ports import ToolResult
    from nucleo.conversation_host.acts import _on_engine_loop
    from nucleo.send import owner
    hint = {k: v for k, v in args.items() if v not in (None, "", [], {})}
    if act:
        hint["_act"] = act
    line = await _on_engine_loop(owner.intake(said() or " ".join(hint.values()), hint, by="call"))
    return ToolResult("ok" if line else "failed", {"say": line} if line else {"reason": "the owner took nothing"})
