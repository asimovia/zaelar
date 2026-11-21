"""A refusal said aloud never names a field or an action of the code — the card's `error` never reaches the mouth.

Measured on a text session (2026-11-16): two `add_reminder` calls were refused with the card's `error` — «no moment to
ring at: notice_at is missing», a sentence written for the MODEL — and, every op of the turn being refused, the turn
handed that sentence to a line composer, which told him: «You'll need to add a notice_at value so I can run it
again.» Taking the code-shaped words out of it first leaves the rest of an instruction to the model («call again
with…») and every field that is one plain word (`date`, `payload`, `startTime`).

The rule is the one every other refusal already follows (`reply.of_op`, V2-652): what he hears is the card's own
`say`/`message`; a refusal with neither is the mouth's plain line, and its `error` stays on the timeline.
"""
from __future__ import annotations

import asyncio
import importlib
import pathlib

import pytest

from nucleo.acts import data_ops

from nucleo.request import refusal_line
from nucleo.workers import spoken_delivery


class _Sp:
    @staticmethod
    def sanitize(t, drop_metadata=False):
        return t


def _turn(res, monkeypatch, mod=data_ops):
    composed, traced = [], []

    async def _line(goal, summary, ok=True, **_k):
        composed.append(summary)
        return f"You'll need to fix this: {summary}"
    monkeypatch.setattr(spoken_delivery, "line", _line)
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: traced.append(k.get("text", "")))
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    sent, done = [], {"v": True}

    async def go():
        async def op():
            return res
        return await mod.say_refusal_instead([("agenda", asyncio.ensure_future(op()))], done, sent.append, _Sp)
    return asyncio.run(go()), composed, done, traced


def test_the_readers_that_took_code_words_out_are_gone():
    assert not hasattr(refusal_line, "without_code") and not hasattr(refusal_line, "codey")
