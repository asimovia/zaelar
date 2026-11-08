"""A failed music act is worded by the turn from its FACTS — never a canned «tell me the artist» after «te la pongo»
(V2-833 F3).

Measured 2026-11-01 on a hosted engine: ten times the model said «te la pongo» and the engine appended the connector's
canned «No he dado con esa canción. ¿Me dices el artista…?», while the cause was ours (the catalogue lookup came back
empty without saying why) and Spotify was connected. The class: an act's outcome reached him as a canned line that
blamed his input. Now the lookup's own outcome travels (`unreachable` is never `no_track`), an unreachable catalogue
skips the web-resolution chain (it cannot help), and the turn's follow-up pass words the facts — SKIP when what was
said still holds — with instructions that are language data in both product languages.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from nucleo.flash import music_outcome


def _res(reason: str, **extra):
    return SimpleNamespace(ok=False, reason=reason, provider="youtube", extra=extra, message="canned")


@pytest.mark.parametrize("code", ["en", "es"])
@pytest.mark.parametrize("reason,option,absent", [("unreachable", "retry", "more_words"), ("no_track", "more_words", "retry"),
                                                   ("needs_app", "open_app", "more_words")])   # V2-860 T4.1
def test_the_facts_say_why_and_offer_only_what_fits(monkeypatch, code, reason, option, absent):
    from i18n import langs
    monkeypatch.setattr(langs, "current_code", lambda: code)
    w = langs.words("music", code=code)
    sys2 = music_outcome.system("LOCK", "pon pa tipos como tú de Shakira", "Te la pongo.", _res(reason, tried="Shakira - Pa tipos como tú"))
    assert w["outcome_reasons"][reason] in sys2 and w["outcome_options"][option] in sys2
    assert w["outcome_options"][absent] not in sys2, "an option that does not fit this outcome was offered"
    assert "«Shakira - Pa tipos como tú»" in sys2 and sys2.startswith("LOCK")


def test_with_words_out_the_round_is_said_in_its_turn_never_detached(monkeypatch):
    """V2-851 F5: no detached follow-up — the play tool's round is said now, glued with a space, or SKIP is silence."""
    from nucleo.flash import follow_up_pass
    assert not hasattr(follow_up_pass, "detach") and not hasattr(follow_up_pass, "deliver"), "a second mouth came back"

    async def _stream(client, sys2, user, spec, mt, what):
        yield "I couldn't reach the music catalogue."
    monkeypatch.setattr(follow_up_pass, "measured", _stream)
    sent: list = []
    out = asyncio.run(music_outcome.say(lang_lock="", asked="play x", said="Playing it now.", res=_res("unreachable"),
                                        spec=None, emit=lambda *a, **k: None, send=sent.append,
                                        speech=SimpleNamespace(sanitize=lambda s, **k: s)))
    assert sent == [" I couldn't reach the music catalogue."] and out == "I couldn't reach the music catalogue."


@pytest.mark.parametrize("model,expected", [("SKIP", []), ("I couldn't reach the music catalogue right now.", ["I couldn't reach the music catalogue right now."])])
def test_with_nothing_said_the_pass_is_the_answer(monkeypatch, model, expected):
    from nucleo.flash import follow_up_pass

    async def _stream(client, sys2, user, spec, mt, what):
        yield model
    monkeypatch.setattr(follow_up_pass, "measured", _stream)
    sent: list = []
    asyncio.run(music_outcome.say(lang_lock="", asked="play x", said="", res=_res("unreachable"), spec=None,
                                  emit=lambda *a, **k: None, send=sent.append, speech=SimpleNamespace(sanitize=lambda s, **k: s)))
    assert sent == expected


@pytest.mark.parametrize("code,kind_word", [("es", "un podcast"), ("en", "a podcast")])
@pytest.mark.parametrize("extra", [{"named": "show"}, {}], ids=["named-by-words", "tapped-by-uri"])
def test_what_was_found_is_named_with_its_kind_and_where(monkeypatch, code, kind_word, extra):
    """V2-860 — the text channel, 2026-11-08: a podcast found on Spotify that could not sound here was worded «the
    album» in «the music app» — the pass had its name and nothing else. Now the facts carry WHAT it is (from the act's
    own kind, or its uri's) and WHERE it was found (the provider that answered). Disarm: `_found_as` → "" → red."""
    from i18n import langs
    monkeypatch.setattr(langs, "current_code", lambda: code)
    res = SimpleNamespace(ok=False, reason="needs_app", provider="spotify",
                          extra={"named_name": "Sueñacuentos", "named_uri": "spotify:show:x1", **extra})
    sys2 = music_outcome.system("LOCK", "pon Sueñacuentos", "", res)
    assert f"«Sueñacuentos» ({kind_word}, Spotify)" in sys2, sys2


@pytest.mark.parametrize("action", ["pause", "next", "resume", "set_volume"])
def test_a_failed_control_is_said_with_the_connectors_line_never_judged(monkeypatch, action):
    """Live 2026-11-08: a refused skip was answered «Done — moving to the next one» and the pass said SKIP over it.
    A control that did not happen is a fact; its sentence is the connector's, and no model may silence it."""
    from nucleo.flash import follow_up_pass

    async def _stream(client, sys2, user, spec, mt, what):
        yield "SKIP"
    monkeypatch.setattr(follow_up_pass, "measured", _stream)
    sent: list = []
    res = SimpleNamespace(ok=False, reason="elsewhere", provider="spotify", action=action, extra={"device": "Camaretas"},
                          message="«Camaretas» está usando Spotify ahora mismo.")
    asyncio.run(music_outcome.say(lang_lock="", asked="x", said="Done.", res=res, spec=None,
                                  emit=lambda *a, **k: None, send=sent.append, speech=SimpleNamespace(sanitize=lambda s, **k: s)))
    assert sent == [" «Camaretas» está usando Spotify ahora mismo."], sent
