"""A turn opened with no user text in context closes quietly (2026-11-18).

It has nothing to answer and nothing went wrong, yet it put «⚠️ Nucleo triggered but no user text in context» on
the session timeline, which read as a fault in every session that had one. Now it returns with no event.
"""
from __future__ import annotations

import asyncio

from nucleo.turn import pipeline_gate


class _Motor:
    def _last_user_text(self, ctx):
        return ""


class _Stream:
    _llm = object()
    _chat_ctx = object()


def test_a_turn_with_no_user_text_returns_without_an_event(monkeypatch):
    seen: list = []
    monkeypatch.setattr("voice.observer.emit", lambda kind, label, **k: seen.append((kind, label)))
    assert asyncio.run(pipeline_gate.open_the_turn(_Stream(), _Motor())) is None
    assert not seen, f"an empty turn is not an event: {seen}"
