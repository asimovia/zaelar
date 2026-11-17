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
from nucleo.turn.prompt import packs as CP
from nucleo.turn.prompt.packs import introduction, presentation


@pytest.fixture
def install(monkeypatch):
    """A brand-new install: settings in a dict, an empty memory, no brief, the agent not renamed."""
    from voice import attention
    store: dict = {}
    monkeypatch.setattr("config.settings.get", lambda k, d=None: store.get(k, d))
    monkeypatch.setattr("config.settings.update", lambda patch: store.update(patch))
    monkeypatch.setattr(introduction, "_known", lambda: {})
    monkeypatch.setattr(introduction, "_RECHECK_S", 0)
    monkeypatch.setattr(attention, "_state", {**attention._state, "assistant_name": ""})
    monkeypatch.setattr("nucleo.turn.brief.of_this_turn", lambda: None)
    monkeypatch.setattr("nucleo.turn.prompt.packs.introduction_block._this_turn", lambda: "T")
    monkeypatch.setattr(presentation, "_pending", "")
    monkeypatch.setattr(introduction, "_offer_pending", "")
    monkeypatch.setattr(introduction, "_turns", 0)
    introduction.install()
    return store


class _Q:
    def __init__(self):
        self.items: asyncio.Queue = asyncio.Queue()

    async def get(self):
        return await self.items.get()


def _close_turn(reply: str) -> None:
    """The turn whose prompt was just composed closes with `reply`, through the phase's own watcher."""
    async def run():
        q = _Q()
        task = asyncio.get_event_loop().create_task(introduction._consume_turns(q))
        await q.items.put({"window": [{"role": "assistant", "text": reply}], "trace": "T"})
        for _ in range(4):
            await asyncio.sleep(0)
        task.cancel()
    asyncio.run(run())


SAID = {"es": "¡Hola! Soy Johnny. Ahora te escucho siempre y respondo a todo; si activas la palabra de activación…",
        "en": "Hi! I'm Johnny. Right now I listen all the time and answer everything; turn on word activation…"}


@pytest.mark.parametrize("code", ["es", "en"])
def test_the_first_prompt_carries_this_languages_presentation_and_its_reply_settles_it(install, monkeypatch, code):
    monkeypatch.setenv("ZAELAR_LANGUAGE", code)
    install["stt_language"] = code
    words = presentation.text("Johnny")
    assert words and "Johnny" in words and "{name}" not in words
    assert words == langs.words("introduction.presentation", code).replace("{name}", "Johnny"), "not this language's"
    first = CP.compose(langs.spec(code).kickoff_prompt)
    assert "PRESENTACIÓN" in first and words in first, first
    _close_turn(SAID[code])
    assert install.get(presentation.FLAG) is True
    assert install.get(introduction.OFFER_FLAG) is True, "the presentation carries the name-and-voice offer"
    again = CP.compose(langs.spec(code).kickoff_prompt)        # a new session's first turn, phase still open
    assert "PRESENTACIÓN" not in again and words not in again, "said twice"
    assert "masculina o femenina" not in again, "the offer it carried was repeated"


@pytest.mark.parametrize("code", ["es", "en"])
def test_each_language_says_every_part_in_its_own_words(code):
    """The five parts the operator listed, in the pack of each language — not a translation done at speaking time."""
    words = langs.words("introduction.presentation", code)
    parts = {"es": ["{name}", "palabra de activación", "nombre", "una sola persona", "¿Cómo te llamas?"],
             "en": ["{name}", "word activation", "name", "one person", "What's your name?"]}[code]
    assert all(p in words for p in parts), words
    assert len(words.split()) <= 70, "too long to speak comfortably"


def test_a_reply_that_did_not_present_itself_leaves_it_for_the_next_turn(install, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")
    install["stt_language"] = "es"
    CP.compose(langs.spec("es").kickoff_prompt)
    _close_turn("¡Hola! ¿En qué te ayudo?")                    # no name: it did not say the presentation
    assert install.get(presentation.FLAG) is None
    assert "PRESENTACIÓN" in CP.compose("vale"), "an unsaid presentation must ride the next (free) turn"


def test_a_turn_that_never_carried_it_settles_nothing(install, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")
    install["stt_language"] = "es"
    _close_turn("¡Hola! Soy Johnny.")                          # no prompt of ours carried it
    assert install.get(presentation.FLAG) is None


def test_the_reset_that_starts_over_says_it_again():
    from config import settings
    assert presentation.FLAG in settings.AGENT_KEYS
