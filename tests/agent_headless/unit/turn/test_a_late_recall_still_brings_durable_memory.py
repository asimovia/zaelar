"""V2-762 — a slow embedding provider DEGRADES the durable recall; it never ERASES it.

Operator, 2026-09-24, over a memory box reading «el recall no cerró en 0.8s — el turno sigue SIN memoria
durable»: *«necesitamos la memoria permanente, ya sea a través del proveedor principal o del de failover…
lo que no podemos es hacer que falle y no tener memoria permanente, porque es la característica más importante
de este proyecto»*.

Measured on his engine that afternoon: the full recall took 1-3.5 s live (0.3-0.5 s alone), almost all of it the
remote embedding call, and every miss left the turn with NO durable memory. The recall has a second channel
that lives on this machine — FTS5, 3-27 ms measured on his database. It now runs BESIDE the full one, and it is
what the turn carries when the full one is late; the full one still reaches the next turn as a note.

And the box: the heart's «is my titular answering» was derived from the ROW's colour, so an amber recall read
«deepseek-flash · deepseek no responde» all afternoon over a heart that wrote every pill normally.
"""
from __future__ import annotations

import asyncio
import json
import time

import pytest

from voice import health_state


def _double(full_s: float, full_block: str, lex_block: str, lex_s: float = 0.0):
    """A compose_recall with the REAL signature — a fixed-signature double would die inside the product's
    `except` on the lexical call and leave these tests measuring nothing (paid before, V2-760)."""
    calls = []

    def _compose(q, timings=None, lexical_only=False):
        calls.append(lexical_only)
        if lexical_only:
            time.sleep(lex_s)
            return (lex_block, [2]) if lex_block else ("", [])
        time.sleep(full_s)
        return (full_block, [1])
    return _compose, calls


def _rows(monkeypatch):
    from voice import observer
    got = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, **k: got.append((kind, label, k)))
    return got


@pytest.fixture(autouse=True)
def _clean_light():
    health_state.clear("memory")
    yield
    health_state.clear("memory")


def test_the_lexical_channel_never_calls_the_embedding_provider(monkeypatch):
    """The whole point of the local half: a remote embedding that hangs cannot reach it."""
    from memory import embeddings, retriever

    def _hang(*_a, **_k):
        raise AssertionError("the lexical recall called the embedding provider")
    monkeypatch.setattr(embeddings, "embed", _hang)
    retriever.search("¿dónde vivo?", limit=5, expand=False, lexical_only=True)


def test_the_hearts_titular_is_judged_by_the_heart_not_by_the_rows_colour(monkeypatch):
    from nucleo.memory_agent.processor import distill_health
    from server import voice_api
    healthy = {"model": "deepseek-flash", "url": "https://api.deepseek.com", "fail_streak": 0,
               "last_error": "", "last_ok_ts": 0.0, "degraded": False}
    monkeypatch.setattr(distill_health, "status", lambda: healthy)
    health_state.record("memory", "degraded", "el recall no cerró en 0.8s — el turno sigue SIN memoria durable")
    payload = json.loads(bytes(asyncio.run(voice_api.status()).body).decode())
    row = next(it for it in payload["items"] if it["key"] == "memory")
    assert row["state"] == "warn"
    assert (row.get("extra") or {}).get("titular_ok") is True, \
        f"an amber RECALL told him the heart's model was not answering: {row}"
    assert not row["detail"].startswith("deepseek-flash"), \
        f"the recall's warning was signed with the distiller's name: {row['detail']}"
