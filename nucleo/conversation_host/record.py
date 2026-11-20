"""The `Record` port: the conversation's pair in the engine's record (V2-941, v3.1 §1.8) — the same `kind='conv'`
rows the old turn writes (`nucleo/turn/pipeline_close.py`), so «what did I tell you yesterday», the day's ledger and
recall see a switched session's conversation like any other. The memory queue writes it; a repeat after a crash
carries the same `conv` ref. And his words of that batch go to the memory agent to be filed (C14b), as the old turn's
gate filed them.
"""
from __future__ import annotations


class MemoryRecord:
    def pair(self, account: str, said: str, answered: str, *, ref: str, channel: str = "voice") -> None:
        from memory import api as memory
        memory.write(f"Operador: {said[:200]} · zaelar: {answered[:200]}", kind="conv", level="short", importance=0.2,
                     ttl_days=2.0, meta={"source": "conv", "u": said[:400], "a": answered[:400], "conv": ref})
        _ingest(said, channel)


def _ingest(said: str, channel: str) -> None:
    """His words of an answered batch to the memory's one writer (`memory_agent.ingest_utterance`), in the background
    on its own loop — what he tells the agent is remembered, as on the old path. A batch closed silent (another voice,
    a word not for us) is never answered, so never filed."""
    if not str(said or "").strip():
        return
    import asyncio

    from nucleo import memory_agent
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:                     # handed over off a loop (a sweep in a thread): the next pair files it
        return
    _PENDING.add(task := loop.create_task(memory_agent.ingest_utterance(       # it routes itself to its home loop
        said, role="operator", channel="typed" if channel == "typed" else "voice")))
    task.add_done_callback(_PENDING.discard)


_PENDING: set = set()                         # the filings in flight, kept alive until they end
