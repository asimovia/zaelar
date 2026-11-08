"""A podcast or a list plays ITSELF, never something else with a similar name (V2-860 T2.2-T2.4).

Measured on a phone (2026-11-07), Spotify connected but no Spotify app open on the phone, so the page player sounds:

  · «pon Sueña cuentos» — Spotify's answer held the podcast «Sueñacuentos», but the start looked up only SONGS and
    played the first one («Sueña», another artist) on the page. The class: «play X» compared his words with songs.
  · he tapped the list «Sueñacuentos» — its uri could not sound on the phone, and the fallback searched the list's
    NAME as an album and played another album, chapter by chapter. The class: a uri traded for a name.

Now the search service's media door (`search.media.named_whole`) tells the whole his words name from a song, and the
connector plays THAT object by its uri where it can sound, else its own SONGS (`catalog.context`); a podcast's
EPISODES are never substituted — on a phone without the provider's app the answer is `needs_app` and nothing sounds.
The Spotify Web API and the page resolver are faked; nothing reaches the network.
Disarm: `named_whole` returning None → «Sueña cuentos» plays the song again (red).
"""
from __future__ import annotations

import importlib

import pytest

from connectors import music
from connectors.music import catalog, registry
from connectors.music import youtube_audio as yta
from connectors.spotify import client

sp_provider = importlib.import_module("connectors.spotify.provider")

PHONE = "mobile:aa11"

SONG = {"id": "t1", "uri": "spotify:track:t1", "name": "Sueña", "artists": [{"name": "Luis Miguel"}]}
SHOW = {"id": "sh1", "uri": "spotify:show:sh1", "name": "Sueñacuentos", "publisher": "Elena Lostalé",
        "total_episodes": 120, "images": []}
LIST = {"id": "pl1", "uri": "spotify:playlist:pl1", "name": "Sueñacuentos", "owner": {"display_name": "Elena"},
        "tracks": {"total": 2}, "images": []}
OTHER_ALBUM = {"id": "al9", "uri": "spotify:album:al9", "name": "Sueñacuentos Estudio",
               "artists": [{"name": "Otro"}], "images": []}
EPISODES = [{"id": "e1", "uri": "spotify:episode:e1", "name": "El dragón que no sabía volar", "duration_ms": 600000},
            {"id": "e2", "uri": "spotify:episode:e2", "name": "La luna dormilona", "duration_ms": 540000}]


@pytest.fixture
def world(monkeypatch, tmp_path):
    """A phone with no Spotify app (no device): Spotify only knows the catalogue, the page player sounds."""
    import widgets.store as store
    from voice import screens
    monkeypatch.setattr(store, "_path", lambda wid: str(tmp_path / f"{wid}.json"))
    monkeypatch.setattr(store, "_legacy_path", lambda wid: str(tmp_path / f"{wid}_legacy.json"))
    monkeypatch.setattr(sp_provider, "_SETTLE_S", 0)
    monkeypatch.setattr(sp_provider.SpotifyProvider, "connected", lambda self: True)
    calls = {"looked": [], "search": [], "album": [], "played": []}
    monkeypatch.setattr(yta, "_resolve", lambda q: (calls["looked"].append(q), ("vid0000001", q))[1])
    answer = {"tracks": {"items": [SONG]}, "shows": {"items": [SHOW]}, "playlists": {"items": [LIST]},
              "albums": {"items": [OTHER_ALBUM]}, "artists": {"items": []}}

    def _search(q, types="track", limit=5):
        calls["search"].append((q, types))
        return {k: v for k, v in answer.items() if k.rstrip("s") in types.split(",") or k == "tracks"}
    monkeypatch.setattr(client, "search", _search)
    monkeypatch.setattr(client, "devices", lambda: [])
    monkeypatch.setattr(client, "album", lambda aid: (calls["album"].append(aid), {**OTHER_ALBUM, "tracks": {
        "items": [{"id": "x", "uri": "spotify:track:x", "name": "Créditos iniciales", "artists": []}]}})[1])
    monkeypatch.setattr(client, "playlist", lambda pid: dict(LIST))
    monkeypatch.setattr(client, "playlist_items", lambda pid, limit=50: [
        {"track": {**e, "type": "episode", "show": {"name": "Sueñacuentos", "images": []}}} for e in EPISODES])
    monkeypatch.setattr(client, "show", lambda sid: {**SHOW, "episodes": {"items": EPISODES}})
    monkeypatch.setattr(client, "play", lambda **k: (calls["played"].append(k), {})[1])
    registry._PROVIDERS.clear()
    registry._loaded = True
    registry.register(sp_provider.SpotifyProvider())
    registry.register(yta.YouTubeAudioProvider())
    screens._reset_for_tests()
    screens.begin_turn(PHONE, "T1")
    yield calls, answer
    screens._reset_for_tests()
    registry._PROVIDERS.clear()
    registry._loaded = False


def test_the_catalogue_search_brings_podcasts(world):
    res = catalog.search("Sueña cuentos")
    assert [s["name"] for s in res["shows"]] == ["Sueñacuentos"] and res["shows"][0]["owner"] == "Elena Lostalé"
    assert "show" in world[0]["search"][0][1].split(",")


@pytest.mark.parametrize("words", ["Sueña cuentos", "sueñacuentos", "Sueñacuentos de Elena Lostalé"])
def test_words_that_name_a_podcast_find_the_podcast_and_a_phone_without_its_app_plays_nothing_else(world, words):
    calls, _ = world
    r = music.control("play", words)
    assert not r.ok and r.reason == "needs_app", r
    assert r.extra.get("named") == "show" and r.extra.get("named_uri") == "spotify:show:sh1"
    assert calls["looked"] == [], "neither the namesake song nor the episode's words sounded on the page"
    from i18n import langs
    assert r.message == langs.words("music.spotify.needs_app_phone", default="").format(
        label="Sueñacuentos", provider="Spotify") and r.message, "the phone's own line"


def test_an_album_his_words_name_plays_its_own_songs(world):
    calls, answer = world
    answer["shows"]["items"], answer["playlists"]["items"] = [], []
    answer["albums"]["items"] = [{"id": "al1", "uri": "spotify:album:al1", "name": "True Blue",
                                  "artists": [{"name": "Madonna"}], "images": []}]
    answer["tracks"]["items"] = [{"id": "t9", "uri": "spotify:track:t9", "name": "Open Your Heart",
                                  "artists": [{"name": "Madonna"}]}]
    r = music.control("play", "True Blue de Madonna")
    assert r.ok and r.extra.get("named") == "album" and calls["album"] == ["al1"]
    assert calls["looked"] and "Créditos iniciales" in calls["looked"][0], "the album's own first song"


def test_an_opened_podcast_marks_its_episodes(world):
    page = catalog.context("spotify:show:sh1")
    assert page and {t.get("kind") for t in page["tracks"]} == {"episode"}
    lst = catalog.context("spotify:playlist:pl1")
    assert lst and all(t.get("kind") == "episode" for t in lst["tracks"])


def test_a_song_title_still_plays_the_song(world):
    calls, answer = world
    answer["tracks"]["items"] = [{"id": "b1", "uri": "spotify:track:b1", "name": "Bohemian Rhapsody",
                                  "artists": [{"name": "Queen"}]}]
    answer["albums"]["items"] = [{"id": "a1", "uri": "spotify:album:a1", "name": "A Night at the Opera",
                                  "artists": [{"name": "Queen"}]}]
    r = music.control("play", "Bohemian Rhapsody")
    assert r.ok and not r.extra.get("named") and calls["looked"] == ["Queen - Bohemian Rhapsody"]


def test_a_tie_between_an_album_and_its_song_keeps_the_song(world):
    _, answer = world
    answer["tracks"]["items"] = [{"id": "t", "uri": "spotify:track:t", "name": "Thriller",
                                  "artists": [{"name": "Michael Jackson"}]}]
    answer["albums"]["items"] = [{"id": "a", "uri": "spotify:album:a", "name": "Thriller",
                                  "artists": [{"name": "Michael Jackson"}]}]
    answer["shows"]["items"], answer["playlists"]["items"] = [], []
    from search import media
    got = media.find_media("Thriller", catalogue=catalog.search)
    assert got["candidates"][0]["kind"] == "track" and media.named_whole("Thriller", got["candidates"]) is None


def test_a_tapped_list_of_episodes_that_cannot_sound_here_says_why_and_plays_nothing_else(world):
    calls, _ = world
    from widgets.musica import data as _md, browse  # noqa: F401 — the card loads browse through data
    out = browse.a_play_album("play_album", {"uri": "spotify:playlist:pl1", "album": "Sueñacuentos"})
    assert not out["ok"] and out["error"] == "needs_app" and out["uri"] == "spotify:playlist:pl1", out
    assert calls["album"] == [], "no album was looked up by the list's name"
    assert not any(q == "Sueñacuentos" for q, _t in calls["search"]), "the list's name was never searched"
    assert calls["looked"] == [], "no episode played by its words on the page"


def test_a_tapped_list_of_songs_that_cannot_sound_here_plays_its_own_songs(world, monkeypatch):
    calls, _ = world
    from widgets.musica import data as _md, browse  # noqa: F401 — the card loads browse through data
    monkeypatch.setattr(client, "playlist_items", lambda pid, limit=50: [
        {"track": {"id": "s1", "uri": "spotify:track:s1", "name": "Nana del caballo", "artists": [{"name": "Tradicional"}]}},
        {"track": {"id": "s2", "uri": "spotify:track:s2", "name": "Duérmete niño", "artists": [{"name": "Tradicional"}]}}])
    out = browse.a_play_album("play_album", {"uri": "spotify:playlist:pl1", "album": "Sueñacuentos"})
    assert out["ok"] and out["tracks"] == 2, out
    assert calls["album"] == [] and calls["looked"] and "Nana del caballo" in calls["looked"][0]


def test_a_tapped_podcast_on_a_phone_without_its_app_says_why(world):
    calls, _ = world
    from widgets.musica import data as _md, browse  # noqa: F401 — the card loads browse through data
    out = browse.a_play_album("play_album", {"uri": "spotify:show:sh1", "album": "Sueñacuentos"})
    assert not out["ok"] and out["error"] == "needs_app" and calls["album"] == [] and calls["looked"] == []


def test_the_cards_search_hands_back_what_can_be_played_with_its_handle(world):
    from widgets.musica import data as _md, browse  # noqa: F401 — the card loads browse through data
    out = browse.a_search("search", {"query": "Sueña cuentos"})
    assert out["ok"] and out["shows"] == 1
    assert out["named"]["kind"] == "show" and out["named"]["uri"] == "spotify:show:sh1"
    assert out["candidates"][0]["uri"] == "spotify:show:sh1" and "item" not in out["candidates"][0]


def test_a_list_that_cannot_be_opened_says_so_and_plays_nothing_else(world, monkeypatch):
    calls, _ = world
    from widgets.musica import data as _md, browse  # noqa: F401 — the card loads browse through data

    def _refused(pid, limit=50):
        raise client.SpotifyError(404, "http", "not found")
    monkeypatch.setattr(client, "playlist_items", _refused)
    out = browse.a_play_album("play_album", {"uri": "spotify:playlist:pl1", "album": "Sueñacuentos"})
    assert not out["ok"] and out["error"] == "context_unreadable"
    assert calls["album"] == [] and calls["looked"] == [], "nothing else sounded in its place"


def test_the_phone_turn_replayed_is_worded_from_what_was_found_never_the_cards_now_playing(world):
    """V2-860 T4.1 — T94 of the archived phone session: «Sueña cuentos en Spotify?» with no Spotify app on the phone.
    The reply said «ahora mismo en Spotify suena Better With Time» — read from the card, not from the act. The act's
    facts now carry what the catalogue found and why it cannot sound here; the card's «now playing» is not a fact."""
    from i18n import langs
    from nucleo.flash import music_outcome
    said = "Voy a buscarlo en Spotify y te lo pongo a sonar."
    res = music.control("play", "Sueña cuentos")
    facts = music_outcome.system("LOCK", "Sueña cuentos en Spotify?", said, res)
    w = langs.words("music", default={})
    assert "«Sueñacuentos»" in facts and w["outcome_reasons"]["needs_app"] in facts
    assert w["outcome_options"]["open_app"] in facts and "Better With Time" not in facts
