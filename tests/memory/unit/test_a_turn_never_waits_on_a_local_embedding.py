"""A read never waits on a LOCAL embedding past its budget (V2-891, node 3.192).

A local embedder (Ollama, fastembed) runs on the host the voice runs on. On a host short of memory its weights are the
pages the OS compressed or swapped out, and one query embedding took seconds while the operator waited for an answer.
The lexical channel (FTS5) lives in the same database and answers in milliseconds. So past `embed_budget_ms` (300 ms,
`config/resources.default.json`) the read goes on with the lexical channel alone, says so on the timeline, and the
abandoned embedding never blocks the next read (a bounded pool). A remote embedder is not bounded here — the turn's
own recall budget runs the lexical lane beside it (`nucleo/turn/recall_budget.py`).

Disarm (seen red): `_LOCAL_BACKENDS = ()` in `memory/retriever/recall.py` → the read waits the full 2 s.
"""
from __future__ import annotations

import time

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import writer as memwriter
from memory.retriever import recall


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("MEMORY_RERANK", "off")
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    memwriter.insert_memory("Su dentista se llama Ramírez y está en la calle Mayor.", level="long", kind="fact")
    memwriter.insert_memory("Prefers window seats on trains.", level="long", kind="fact")
    yield
    memdb.reset_db()
    mememb.reset()


def _slow_local(monkeypatch, seconds: float = 2.0, backend: str = "fastembed"):
    real = mememb.embed

    def _slow(text):
        time.sleep(seconds)
        return real(text)
    monkeypatch.setattr(recall._emb, "embed", _slow)
    monkeypatch.setattr(recall._emb, "active_backend", lambda: backend)


def test_a_slow_local_embedding_falls_to_the_lexical_channel_within_its_budget(fresh_db, monkeypatch):
    _slow_local(monkeypatch)
    seen = []
    monkeypatch.setattr(recall, "_note_embed_over_budget", lambda ms: seen.append(ms))
    t0 = time.perf_counter()
    hits = recall.search("dentista Ramírez", limit=5)
    took_ms = (time.perf_counter() - t0) * 1000
    assert took_ms < 400, f"the read waited {took_ms:.0f} ms on a local embedding"
    assert any("Ramírez" in h["text"] for h in hits), "the lexical channel did not carry the read"
    assert seen and seen[0] == pytest.approx(300, abs=1), "a read over budget must say so on the timeline"


def test_a_stuck_embedding_never_blocks_the_next_read(fresh_db, monkeypatch):
    _slow_local(monkeypatch)
    t0 = time.perf_counter()
    for _ in range(4):                                   # more reads than the pool has threads
        recall.search("trains window", limit=5)
    assert (time.perf_counter() - t0) * 1000 < 4 * 400


def test_the_budget_is_declared_data(monkeypatch):
    import json
    from pathlib import Path
    declared = json.loads((Path(__file__).resolve().parents[3] / "config/resources.default.json").read_text())
    assert declared["embed_budget_ms"] == 300
    monkeypatch.setenv("ZAELAR_EMBED_BUDGET_MS", "120")
    assert recall._embed_budget_s() == pytest.approx(0.12)


def test_a_remote_embedder_is_not_bounded_here(fresh_db, monkeypatch):
    calls = []
    monkeypatch.setattr(recall._emb, "active_backend", lambda: "cloud")
    real = mememb.embed
    monkeypatch.setattr(recall._emb, "embed", lambda t: (calls.append(t), time.sleep(0.4), real(t))[-1])
    recall.search("dentista", limit=3)
    assert calls == ["dentista"], "the remote embedder is the turn's own recall budget's to bound"
