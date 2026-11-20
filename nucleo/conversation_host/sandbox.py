"""A disposable engine's reset between two isolated test conversations (V2-941; `/api/debug/conversation/reset`).

Only a sandbox (`ZAELAR_CONVERSATION_SANDBOX=1`, set by `tests/conversation/e2e/sandbox.py`) is reset; a real account's
conversation goes on across sessions. The reset leaves nothing of the cases before it:

  · the conversation: its sessions closed, the open one forgotten, its rows gone and its lease fenced (the next
    manager takes the next epoch, so no id names two conversations), its proof counters gone;
  · what the cases WROTE to memory: the first reset marks where the cases begin (after the seed); every reset forgets
    what was written since that mark, and the conversation buffer (`kind='conv'`) whatever its age.
"""
from __future__ import annotations

import os

ENV = "ZAELAR_CONVERSATION_SANDBOX"
_mark: dict = {"memory": None}


def is_sandbox() -> bool:
    return (os.getenv(ENV) or "").strip() == "1"


def forget_cases() -> int:
    """What the cases before this reset wrote to memory: invalidated (soft). The first call only marks."""
    from memory import api as memory
    if _mark["memory"] is None:
        _mark["memory"] = memory.high_water()
        return memory.clear_conversation()
    return memory.forget_after(_mark["memory"]) + memory.clear_conversation()


def reset() -> dict:
    """The whole reset, off the loop (it reads the account and writes the database)."""
    from memory.api import conv
    from nucleo.conversation_host import boot, entry, proof, sessions
    sessions.close_all()
    entry.reset()
    acct = boot.account()
    proof.forget(acct)
    return {"rows": conv.wipe(acct), "memories": forget_cases()}
