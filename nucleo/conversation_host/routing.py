"""The `Route` port (INI-078 F2 steps 3-4, R-3, segregation S4): NOTHING decides his words before the model. The
port only keeps the batch in course (`said`, and his sentences before it); the model is the one decider — an open task
by its #number (`task_say`), the open message draft by its #number (`draft_edit` · `draft_send` · `draft_drop`).

The send owner does not speak by itself: the line it would say is handed back for the manager's mouth. It runs on the
engine's loop. The send act hands HIS words to the owner with the model's call, which takes the call's fields only for
what his words leave empty.
"""
from __future__ import annotations

_last = dict(said="", ours="", his=[])     # a record of the batch in course, never a table
#: how many of his earlier sentences the owner reads beside the one now
BEFORE = 2


def ours_heard(text: str) -> None:
    """A line of ours that SOUNDED (what of it he heard) or was shown: the last line the owner reads his answer against,
    and — when it is the open draft's confirmation — the one thing a go-ahead can answer (`send.heard.heard`)."""
    if not str(text or "").strip():
        return
    _last["ours"] = str(text)
    try:
        from nucleo.send import heard
        heard.heard(str(text), spoken=True)
    except Exception as e:  # noqa: BLE001 — an unreadable draft only means the confirmation is read again
        __import__("logging").getLogger("zaelar.conversation_host").debug(f"routing: heard not noted ({e!r})")


def _his(text: str) -> list[str]:
    """His sentences before this one (the owner reads the last ones beside it), and this one kept for the next."""
    before = list(_last["his"][-BEFORE:])
    _last["his"] = (_last["his"] + [text])[-BEFORE:]
    return before


def said() -> str:
    """His words in the batch the manager is answering now (one batch at a time per account)."""
    return _last["said"]


class HostRoute:
    """The port before the model: it KEEPS his words of the batch and takes none (S4 — one decider: the model)."""

    async def take(self, account: str, text: str) -> str | None:
        _last["said"] = text
        _his(text)
        return None


async def send(args: dict, act: str = "") -> "object":
    """The model's message call — or a widget's message act (`act`, with its payload) — handed to the send owner with
    his words: the owner's line (always a question until his yes) is what the reply says. Nothing leaves here."""
    from conversation.ports import ToolResult
    from nucleo.conversation_host.acts_widget import _on_engine_loop
    from nucleo.send import owner
    hint = {k: v for k, v in args.items() if v not in (None, "", [], {})}
    if act:
        hint["_act"] = act
    line = await _on_engine_loop(owner.intake(said() or " ".join(hint.values()), hint, last_line=_last["ours"],
                                              before=list(_last["his"][:-1][-BEFORE:]), by="call"))
    if not line:
        return ToolResult("failed", {"reason": "the owner took nothing"})
    return ToolResult("ok", {"say": line, "says": "door"})       # the owner's own line: said as it is, never reworded


async def draft(op: str, args: dict) -> "object":
    """The model's act on the open draft by its #number (`send/by_number`): the owner's line is what the reply says."""
    from conversation.ports import ToolResult
    from nucleo.conversation_host import acts_tasks
    from nucleo.conversation_host.acts_widget import _on_engine_loop
    from nucleo.send import by_number
    which = str(args.get("task") or "").strip()
    found, line = await _on_engine_loop(by_number.act(op, which, args, said(), _last["ours"]))
    if not found:
        return acts_tasks._not_open(which)
    if (d := by_number._draft.current()) is not None:      # his turn is seen in the order that opened it (P3)
        from nucleo.conversation_host import turns
        from voice import trace
        turns._merge(getattr(d, "trace", ""), trace.current())
    return ToolResult("ok", {"say": line, "says": "door"} if line else {"task": which})
