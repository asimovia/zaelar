"""The first turn's conversation row is stamped as a KICKOFF (V2-865).

The first turn is the engine speaking in HIS voice (the i18n `kickoff_prompt`) so the model greets him; it is
written into the `conv` buffer as his words. The day's ledger (`memory.day_ledger`) must know it is not something
he said — a greeting must never open an episode, and it marks the start of a new work session. The stamp is
`meta.kickoff=True` on that row, written by the one door that writes the turn's conversation row
(`nucleo/turn/pipeline_close.close_the_turn`); a normal turn's row carries no stamp.
"""
import asyncio
import inspect
import time
from unittest.mock import MagicMock

import pytest

from nucleo.turn import pipeline_close


def _close(first_turn: bool) -> None:
    kw = {name: MagicMock() for name in inspect.signature(pipeline_close.close_the_turn).parameters}
    kw.update(acted={"widget": False}, confirm_state={}, clarify={}, timings={}, llm_metrics={},
              _tool_fired=set(), first_turn=first_turn, operator_text="hola", spoken_text="hey", text="hola")
    for flag in ("data_done", "worker_acted", "style_fired", "deduped", "aside"):
        kw[flag] = {"v": False}
    for req in ("escalate_req", "search_req", "music_req", "images_req", "listing_req", "read_req", "recall_req",
                "reopen_req", "reveal_req"):
        kw[req] = {"v": None}
    for clock in ("t0", "_t_entry", "first_ms", "_acc_ms", "_amap_ms", "_gate_ms"):
        kw[clock] = time.perf_counter()
    kw["brain"]._window = []
    asyncio.run(pipeline_close.close_the_turn(**kw))


@pytest.fixture
def conv_rows(monkeypatch):
    from memory import api as memory
    rows: list[dict] = []
    monkeypatch.setattr(memory, "write", lambda *a, **k: rows.append(k) if k.get("kind") == "conv" else None)
    return rows


def test_the_first_turns_row_carries_the_kickoff_stamp(conv_rows):
    _close(first_turn=True)
    assert len(conv_rows) == 1
    assert conv_rows[0]["meta"].get("kickoff") is True
    assert conv_rows[0]["meta"]["u"] == "hola" and conv_rows[0]["meta"]["a"] == "hey"


def test_a_normal_turns_row_carries_none(conv_rows):
    _close(first_turn=False)
    assert len(conv_rows) == 1
    assert "kickoff" not in conv_rows[0]["meta"]
