"""The `Route` port (INI-078 F2 steps 3-4, plan §3; R-3): his words to an open message DRAFT reach its owner before
the model is called — the send owner reads the sentence against that one draft (`nucleo.send.owner.take`): who, what
it says, send it, drop it — taken, its line is said; anything else goes on to the model. A process in course or a row
waiting on his answer is the MODEL's to answer (`task_answer`, R-3): no router decides it before the model.

The owner does not speak by itself: the line it would say is handed back for the manager's mouth. It runs on the
engine's loop. The words of the batch in course are kept (`said`): the send act hands them to the owner with the model's
call, which reads HIS words and takes the call's fields only for what they leave empty.
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
    """The one door before the model for his words: an open message draft reads them first (its owner reads a sentence
    against ONE concrete draft, it guesses nothing). A process in course or waiting on him is NOT routed here any more
    (R-3): the model sees it in TASKS and answers it with `task_answer`."""

    async def take(self, account: str, text: str) -> str | None:
        """In the trace of the turn in course: what the owner emits is the order's flow."""
        from nucleo.conversation_host import turns
        from voice import trace
        with trace.scope(turns.current()):
            return await self._take(text)

    async def _take(self, text: str) -> str | None:
        from nucleo.conversation_host.acts_widget import _on_engine_loop
        from nucleo.send import draft, owner
        _last["said"] = text
        before = _his(text)
        if (d := draft.current()) is not None:
            took, line = await _on_engine_loop(owner.take(text, last_line=_last["ours"], before=before))
            if took:                             # his later turn is seen inside the order that opened the draft (P3)
                from nucleo.conversation_host import turns
                from voice import trace
                turns._merge(getattr(d, "trace", ""), trace.current())
                return line or ""
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
