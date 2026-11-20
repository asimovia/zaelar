"""The `Memory` port of a switched session (V2-941, the F1 plan §4.7, v3.1 B4): it reads the state the way the rest of
the engine reads it, and writes nothing.

  state_blocks   STATE (what the memory knows that is not the conversation, as facts with plain labels), the widgets on
                 screen and used lately, and the tasks running or waiting — each bounded, all within the run's token
                 budget. Facts, never another prompt's prose: no heading, no instruction, no copy of the conversation. The notices owed are NOT
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
    """What the memory knows that is not the conversation, as FACTS with plain labels: how he likes to be treated,
    where he is, the critical facts, the mission, the salient things and the errands. Never the old turn's composed
    block — its headings, its instructions to the model and its copy of the conversation (the manager has its own
    CONVERSATION): its «you are called X» under «who is in front of you» made the model call him by the
    assistant's name, and its words in one language dragged the replies there."""
    from memory import api as memory
    st = memory.state() or {}
    lines = [f"{label}: {str(st[key]).strip()}" for key, label in FIELDS if str(st.get(key) or "").strip()]
    critical = [str(c).strip() for c in memory.critical_facts(limit=6) if str(c).strip()]
    if critical:
        lines.append("critical: " + " · ".join(critical))
    for m in memory.salient_long(limit=5, max_chars=440):
        text = str(m.get("text") or "").strip().replace("\n", " ")[:140]
        if text:
            lines.append(f"{KIND_LABELS.get(str(m.get('kind') or ''), 'known')}: {text}")
    return "\n".join(lines)


#: the memory state's fields this block reads, each with its label
FIELDS = (("treatment", "treatment"), ("location", "location"), ("mission", "mission"))
#: a salient memory's kind → its label: an errand is not a fact about him
KIND_LABELS = {"request": "he asked", "result": "delivered"}


def _widgets() -> str:
    """Which widgets are on screen and which were used lately, by id (each one's purpose is the catalogue's)."""
    from nucleo.turn.prompt import live_state
    open_ids, recent = list(live_state._open_widget_ids() or ()), list(live_state._recent_widget_ids() or ())
    out = [f"on screen: {', '.join(open_ids)}"] if open_ids else []
    rest = [w for w in recent if w not in open_ids]
    return "\n".join(out + ([f"used lately: {', '.join(rest)}"] if rest else []))


def _tasks() -> str:
    """The background tasks in course and those waiting for his answer, as facts: name, step, progress, note."""
    from nucleo import dispatch
    from nucleo.circuit import ledger
    lines = []
    for t in dispatch.pending_summaries() or ():
        bits = [str(t.get("name") or t.get("title") or t.get("id") or "").strip()]
        bits += ["not started"] if t.get("held") else ([str(t["phase"]).strip()] if t.get("phase") else [])
        if t.get("total"):
            bits.append(f"step {min(t.get('done', 0), t['total'])}/{t['total']}")
        if (t.get("pct") if t.get("pct") is not None else -1) >= 0:
            bits.append(f"{t['pct']}%")
        if t.get("note"):
            bits.append(str(t["note"]).strip()[:160])
        lines.append("running: " + " · ".join(b for b in bits if b))
    for r in ledger.store().tasks_where(states=("waiting",), visible_only=False, limit=20):
        if str(r.get("waiting_for") or "") == ledger.USER_ANSWER:
            goal = str(r.get("title") or r.get("goal") or "").strip().replace("\n", " ")[:90]
            lines.append(f"waiting for his answer: [{r.get('id')}] {goal} — asked: {str(r.get('ask') or '').strip()[:120]}")
    return "\n".join(lines[:12])


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
