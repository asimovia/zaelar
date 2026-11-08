"""A worker that needs a song, a podcast or a video reaches OUR players through the door it already has (V2-860 T3.2).

Measured on a phone (2026-11-07, T96): a generic worker asked the network («a shopping agent, no use»), drove the
headless browser at open.spotify.com (HTTP 500 twice) and found the podcast seven minutes after the turn — while the
music card's own search answers from the connected catalogue. No new tool: `widget_data` on the card's declared
actions is ALLOWED (FAST) by the worker policy, the card's `search` hands back playable candidates with their `uri`,
and `play_album {uri}` takes the one rule the voice takes (`music.play_whole`). The worker's level 1 says so (the
`search` family, first). Disarm: `a_search` without candidates → red.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from nucleo.cli import worker_api_exec as W
from nucleo.cli import worker_policy as P

ANSWER = {"source": "spotify", "tracks": [{"title": "Sueña", "artist": "Otro", "uri": "spotify:track:1", "source": "spotify"}],
          "artists": [], "albums": [], "playlists": [],
          "shows": [{"name": "Sueñacuentos", "owner": "Elena Lostalé", "uri": "spotify:show:9", "source": "spotify"}]}


@pytest.fixture
def card(monkeypatch, tmp_path):
    import widgets.store as store
    from connectors import music
    from connectors.music import catalog
    monkeypatch.setattr(store, "_path", lambda wid: str(tmp_path / f"{wid}.json"))
    monkeypatch.setattr(store, "_legacy_path", lambda wid: str(tmp_path / f"{wid}_legacy.json"))
    monkeypatch.setattr(catalog, "search", lambda q, limit=8: dict(ANSWER, query=q))
    played = []

    def _whole(uri, name="", kind="", *, opened=None):
        played.append(uri)
        return music.MusicResult(ok=True, provider="spotify", action="play", message="ok")
    monkeypatch.setattr(music, "play_whole", _whole)
    return played


def _act(action, payload):
    rec = SimpleNamespace(task_id="7", trace_id="", sheet="")
    return asyncio.run(W._exec_allow("widget_data", {"widget_id": "musica", "action": action, "payload": payload}, rec))


def test_the_policy_lets_a_worker_search_and_play_on_the_music_card():
    for action, payload in (("search", {"query": "x"}), ("play_album", {"uri": "spotify:show:9"})):
        assert P.classify_act("widget_data", {"widget_id": "musica", "action": action, "payload": payload}) == P.ALLOW


def test_the_cards_search_hands_a_worker_playable_candidates(card):
    out = _act("search", {"query": "Sueña cuentos"})
    assert out["ok"], out
    res = out["result"]["data"]
    assert res["named"]["uri"] == "spotify:show:9" and res["candidates"][0]["kind"] == "show"


def test_play_album_by_uri_takes_the_one_play_rule(card):
    out = _act("play_album", {"uri": "spotify:show:9"})
    assert out["ok"] and card == ["spotify:show:9"], (out, card)


def test_the_workers_first_level_names_our_search_and_the_players_first():
    from nucleo.workers.prompts import catalog
    assert catalog.FAMILIES[0] == "search"
    first = catalog.headlines().splitlines()[1]
    assert "search" in first and "musica" in first and "youtube" in first and "use_tool" in first


def test_the_network_is_asked_first_only_for_what_none_of_ours_covers():
    """T3.4 — both workers: the step-0 block and the headline demote the network to what we lack (decision §8.5)."""
    from nucleo.workers.prompts.context import _mesh_first_block
    for browser in (True, False):
        head = _mesh_first_block(browser=browser).splitlines()[0]
        assert "NADA nuestro cubre" in head and "música y vídeo son nuestros" in head, head


def test_the_widgets_family_gives_each_card_its_mission():
    """T3.3 — level 2 lists `id — whenToUse`, cut like the voice turn's brief cuts it."""
    from nucleo.workers.prompts import catalog
    rows = [ln for ln in catalog.full("widgets").splitlines() if ln.startswith("  · ")]
    musica = next(ln for ln in rows if ln.startswith("  · musica"))
    assert " — " in musica and len(musica.split(" — ", 1)[1]) <= catalog._MISSION_CAP + 1
