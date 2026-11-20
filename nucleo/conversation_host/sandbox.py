"""A disposable engine's reset between two isolated test conversations (V2-941; `/api/debug/conversation/reset`).

Only a sandbox is reset — TWO marks, both the launcher's (`tests/conversation/e2e/sandbox.py`): the environment
(`ZAELAR_CONVERSATION_SANDBOX=1`) and a file it writes in the engine's own workspace (`ZAELAR_WORKSPACE`); a real
account's conversation goes on across sessions. The conversation is closed first, then the memory's queue drains, then
the rest goes. The reset leaves nothing of the cases before it:

  · the conversation: its sessions closed, the open one forgotten, its rows gone and its lease fenced (the next
    manager takes the next epoch, so no id names two conversations), its proof counters gone;
  · what the cases WROTE to memory: the first reset marks where the cases begin (after the seed); every reset forgets
    what was written since that mark, and the conversation buffer (`kind='conv'`) whatever its age;
  · the notices written since the same mark, and the lines the owed port had handed over.
"""
from __future__ import annotations

import os

ENV = "ZAELAR_CONVERSATION_SANDBOX"
#: the launcher's file in the engine's workspace: an environment variable alone does not make an engine disposable
MARKER = ".conversation-sandbox"
_mark: dict = {"memory": None, "notices": None}


def is_sandbox() -> bool:
    from pathlib import Path
    ws = (os.getenv("ZAELAR_WORKSPACE") or "").strip()
    return (os.getenv(ENV) or "").strip() == "1" and bool(ws) and (Path(ws) / MARKER).is_file()


def forget_cases() -> int:
    """What the cases before this reset wrote to memory: invalidated (soft). The first call only marks."""
    from memory import api as memory
    from memory.api import notices
    from nucleo.conversation_host import owed
    owed._handed.clear()
    if _mark["memory"] is None:
        _mark["memory"], _mark["notices"] = memory.high_water(), notices.high_water()
        return memory.clear_conversation()
    return (memory.forget_after(_mark["memory"]) + memory.clear_conversation()
            + notices.forget_after(_mark["notices"]))


def close() -> None:
    """The conversation stopped first: nothing of it writes while the rest goes."""
    from nucleo.conversation_host import entry, sessions
    sessions.close_all()
    entry.reset()


def reset() -> dict:
    """The rest, off the loop (it reads the account and writes the database), once `close` ran and the queue drained."""
    from memory.api import conv
    from nucleo.conversation_host import boot, proof
    acct = boot.account()
    proof.forget(acct)
    return {"rows": conv.wipe(acct), "memories": forget_cases()}
