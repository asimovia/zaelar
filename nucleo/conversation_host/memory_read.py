"""The `Memory` port of a switched session (V2-941, the F1 plan §4.7, v3.1 B4): it reads the state the way the rest of
the engine reads it, and writes nothing.

  state_blocks   STATE (the memory's composed state: mission, situation, what is salient), the widgets brief and the
                 tasks pending or waiting — each bounded, all within the run's token budget. The notices owed are NOT
                 here: the manager says them itself, as they are, and a line in the state too would be told twice
  screen         what is on screen now
  recall         his memory for a query, with no reinforcement

Every read runs in a thread: a slow store delays this run's state, never the loop. A reader that fails leaves its
block out and says nothing else — the state goes without it this time.
"""
from __future__ import annotations

import asyncio
import logging

from conversation.ports import Block

logger = logging.getLogger("zaelar.conversation_host.memory_read")
CHARS_PER_TOKEN = 4


def _state() -> str:
    from memory import api as memory
    return memory.compose_state()[0]


def _widgets() -> str:
    from nucleo.turn.prompt import live_state
    from widgets import brief
    return brief.for_prompt(live_state._open_widget_ids(), live_state._recent_widget_ids())


def _tasks() -> str:
    from nucleo.turn.prompt import live_tasks
    return "\n".join(live_tasks.pending_task_lines() + live_tasks.waiting_lines())


READERS = (("STATE", _state), ("WIDGETS", _widgets), ("TASKS", _tasks))


def _blocks(budget_tokens: int) -> list[Block]:
    share = max(1, budget_tokens * CHARS_PER_TOKEN // len(READERS))
    out = []
    for title, read in READERS:
        try:
            text = (read() or "").strip()
        except Exception as e:  # noqa: BLE001 — a reader that fails leaves its block out, this time
            logger.debug(f"memory_read: {title} unreadable ({e!r})")
            continue
        if text:
            out.append(Block(title, text[:share]))
    return out


class MemoryRead:
    async def state_blocks(self, account: str, *, budget_tokens: int) -> list[Block]:
        return await asyncio.to_thread(_blocks, budget_tokens)

    async def screen(self, account: str, endpoint: str | None) -> Block:
        from nucleo.turn.prompt import live_state
        return Block("SCREEN", await asyncio.to_thread(live_state.screen_line))

    async def recall(self, account: str, query: str, *, k: int) -> list[Block]:
        from memory import api as memory
        got = await asyncio.to_thread(memory.query, query, limit=k, reinforce_used=False)
        return [Block("RECALL", str(m.get("text") or ""), str(m.get("id") or "")) for m in got.get("memories") or []]
