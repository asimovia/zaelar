"""The `Record` port: the conversation's pair in the engine's record (V2-941, v3.1 §1.8) — the same `kind='conv'`
rows the old turn writes (`nucleo/turn/pipeline_close.py`), so «what did I tell you yesterday», the day's ledger and
recall see a switched session's conversation like any other. The memory queue writes it; a repeat after a crash
carries the same `conv` ref.
"""
from __future__ import annotations


class MemoryRecord:
    def pair(self, account: str, said: str, answered: str, *, ref: str) -> None:
        from memory import api as memory
        memory.write(f"Operador: {said[:200]} · zaelar: {answered[:200]}", kind="conv", level="short", importance=0.2,
                     ttl_days=2.0, meta={"source": "conv", "u": said[:400], "a": answered[:400], "conv": ref})
