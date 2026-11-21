"""The first-run presentation is said ONCE per install, in his language, and then never again (V2-929).

The operator, 2026-11-17: on a new install the agent's first words say that it is Johnny, that it answers everything
and listens all the time for now but word activation makes it answer only when called by name, that its name is his
to change, that it answers to one operator though others may talk with it — and ask his name. Said once, marked, never
repeated; a reset that starts the relationship over says it again.

What is pinned, each with its red disarm:
1. the first prompt of an install carries THE language's presentation, with the catalogue's name in it (es · en);
2. the turn that carried it settles it only when its reply named the agent — and then the next first turn of a new
   session carries no presentation (said once), but the bare offer is not repeated either (the presentation told it);
3. the flag is an agent-side key, so the reset that starts over drops it.
"""
from __future__ import annotations

import asyncio

import pytest

from i18n import langs


class _Q:
    def __init__(self):
        self.items: asyncio.Queue = asyncio.Queue()

    async def get(self):
        return await self.items.get()


SAID = {"es": "¡Hola! Soy Johnny. Ahora te escucho siempre y respondo a todo; si activas la palabra de activación…",
        "en": "Hi! I'm Johnny. Right now I listen all the time and answer everything; turn on word activation…"}


@pytest.mark.parametrize("code", ["es", "en"])
def test_each_language_says_every_part_in_its_own_words(code):
    """The five parts the operator listed, in the pack of each language — not a translation done at speaking time."""
    words = langs.words("introduction.presentation", code)
    parts = {"es": ["{name}", "palabra de activación", "nombre", "una sola persona", "¿Cómo te llamas?"],
             "en": ["{name}", "word activation", "name", "one person", "What's your name?"]}[code]
    assert all(p in words for p in parts), words
    assert len(words.split()) <= 70, "too long to speak comfortably"

