"""Tests for nucleo/flash/music_flow.py (V2-042) — the music rail's resolve→validate→act chain."""
import asyncio

import pytest

from connectors.music.base import MusicResult, Track
from nucleo import rails
from nucleo.flash import music_flow


@pytest.fixture(autouse=True)
def _iso(monkeypatch):
    """Isolate rails (captured projection) + memory (captured ingest) + LANGUAGE.

    The language is set deliberately: this file checks PHRASES spoken to the operator («ask for the artist»),
    and since the language-startup change (2026-08-09), the product starts in ENGLISH and only switches to the
    operator's language when it detects it. Without fixing it, the test inherited the machine's ENVIRONMENT
    language: it passed on the operator's machine —which has Spanish in its config— and failed anywhere else
    and in CI, even though nothing was wrong with the product. A phrase test must specify which language it expects."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")
    ingested = []
    from memory import api as mapi
    monkeypatch.setattr(mapi, "set_state", lambda fields: fields)
    monkeypatch.setattr(mapi, "ingest_message",
                        lambda source, entity, text, **kw: ingested.append({"source": source, "entity": entity,
                                                                            "text": text, **kw}))
    rails._RUNS.clear()
    yield ingested
    rails._RUNS.clear()


def _track(title="Come Fly With Me", artist="Frank Sinatra"):
    return Track(id="t1", uri="spotify:track:t1", title=title, artist=artist)


def _ok(action="play", track=None, provider="spotify"):
    return MusicResult(ok=True, provider=provider, action=action, track=track, message="Suena x.")


def _no_track(q=""):
    return MusicResult(ok=False, provider="spotify", action="play", reason="no_track", message=f"No encontré «{q}».")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_direct_hit_plays_updates_rails_and_memory(_iso, monkeypatch):
    monkeypatch.setattr("connectors.music.control",
                        lambda action, q="", uri="", pct=0, prefer="": _ok(track=_track()))
    res = _run(music_flow.run("play", "frank sinatra"))
    assert res.ok
    assert rails.get("music.search") is None                       # no chain → no search run
    playing = rails.get("music.playing")
    assert playing and "Come Fly With Me" in playing["label"] and playing["status"] == "playing"
    assert _iso and _iso[0]["source"] == "music" and _iso[0]["entity"] == "Frank Sinatra"
    assert "Sonó «Come Fly With Me»" in _iso[0]["text"]


def test_chain_resolves_fuzzy_via_websearch_and_extract(_iso, monkeypatch):
    calls = []

    def _control(action, q="", uri="", pct=0, prefer=""):
        calls.append(q)
        if q == "esa que dice vuela conmigo":
            return _no_track(q)
        return _ok(track=_track())                                  # the canonical query succeeds

    monkeypatch.setattr("connectors.music.control", _control)
    monkeypatch.setattr("search.web.search", lambda q, k=5: {"results": [{"title": "Come Fly With Me - Wikipedia",
                                                                                "snippet": "Frank Sinatra song"}]})
    monkeypatch.setattr("search.web.format_results", lambda res, limit=5: "Come Fly With Me — Frank Sinatra")

    async def _extract(sys, user):
        assert "vuela conmigo" in user
        return "Frank Sinatra - Come Fly With Me"

    res = _run(music_flow.run("play", "esa que dice vuela conmigo", extract=_extract))
    assert res.ok and res.extra.get("resolved_from") == "esa que dice vuela conmigo"
    assert calls == ["esa que dice vuela conmigo", "Frank Sinatra - Come Fly With Me"]
    assert rails.get("music.search") is None                        # resolved → disappears
    assert rails.get("music.playing")["status"] == "playing"
    assert _iso and "la pidió como" in _iso[0]["text"]              # writeback stores the original track


def test_chain_fail_keeps_isolated_run_and_asks_more(_iso, monkeypatch):
    monkeypatch.setattr("connectors.music.control",
                        lambda action, q="", uri="", pct=0, prefer="": _no_track(q))
    monkeypatch.setattr("search.web.search", lambda q, k=5: {"results": []})
    monkeypatch.setattr("search.web.format_results", lambda res, limit=5: "")

    async def _extract(sys, user):
        raise AssertionError("sin contexto no se llama al extractor")

    res = _run(music_flow.run("play", "tararara la del verano", extract=_extract))
    assert res.ok is False
    a = rails.get("music.search")
    assert a and a["status"] == "sin_resolver" and a["attempts"] == 1
    # Changed on purpose (V2-833 F3): no canned «¿me dices el artista?» — the turn words the outcome from its facts
    # (`music_outcome`, node of test_a_failed_song_is_worded_from_its_facts); the facts carry what was tried.
    assert res.reason == "no_track" and res.extra.get("tried") == "tararara la del verano"
    assert not _iso                                                 # nothing played → nothing to memory


def test_extract_no_means_unresolved(monkeypatch):
    monkeypatch.setattr("connectors.music.control",
                        lambda action, q="", uri="", pct=0, prefer="": _no_track(q))
    monkeypatch.setattr("search.web.search", lambda q, k=5: {"results": [{"t": "x"}]})
    monkeypatch.setattr("search.web.format_results", lambda res, limit=5: "resultados varios")

    async def _extract(sys, user):
        return "NO"

    res = _run(music_flow.run("play", "mmm nose", extract=_extract))
    assert res.ok is False and rails.get("music.search")["status"] == "sin_resolver"


def test_pause_reflects_in_playing_run(monkeypatch):
    monkeypatch.setattr("connectors.music.control",
                        lambda action, q="", uri="", pct=0, prefer="": _ok(action=action, track=_track() if action == "play" else None))
    # Since 2026-11-08 a spoken control is the music card's own action (`music_flow._through_card`).
    async def _card(wid, action, payload):
        assert (wid, action) == ("musica", "pause")
        return {"ok": True, "message": "", "reason": "", "provider": "spotify"}
    monkeypatch.setattr("widgets.server_api.brain_action", _card)
    _run(music_flow.run("play", "sinatra"))
    _run(music_flow.run("pause", ""))
    assert rails.get("music.playing")["status"] == "paused"


def test_parse_canonical():
    assert music_flow._parse_canonical("Frank Sinatra - Come Fly With Me") == "Frank Sinatra - Come Fly With Me"
    assert music_flow._parse_canonical("NO") == ""
    assert music_flow._parse_canonical("no estoy seguro") == ""
    assert music_flow._parse_canonical("") == ""
    assert music_flow._parse_canonical("«Rosalía — Despechá»") == "Rosalía — Despechá"


@pytest.mark.parametrize("spoken, card", [("pause", "pause"), ("stop", "pause"), ("resume", "resume"),
                                          ("next", "next"), ("previous", "previous"), ("volume_up", "volume_up")])
def test_a_spoken_control_is_the_music_cards_own_action(monkeypatch, spoken, card):
    """Operator, 2026-11-08: «cuando digo pausa, el widget pausa y lanza la señal al conector». A spoken control runs
    the card's declared action — the same funnel as his tap — never a second road straight to the connector."""
    direct: list = []
    monkeypatch.setattr("connectors.music.control", lambda *a, **k: direct.append(a) or _ok())
    seen: list = []

    async def _card(wid, action, payload):
        seen.append((wid, action))
        return {"ok": True, "message": "", "reason": "", "provider": "spotify"}
    monkeypatch.setattr("widgets.server_api.brain_action", _card)
    res = _run(music_flow.run(spoken, ""))
    assert res.ok and seen == [("musica", card)] and direct == [], (seen, direct)
