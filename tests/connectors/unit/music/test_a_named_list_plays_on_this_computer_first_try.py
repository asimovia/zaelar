"""A list he names plays on the first try, on the Spotify of the computer that asked (V2-861).

Replays a session measured on a local engine (2026-11-08): a desktop screen, Spotify connected and its app open on that
same computer, and «put some list in spotify. Look for sueñacuentos and play it». The catalogue held ONE podcast and
FOUR lists named «Sueñacuentos». Four turns answered `needs_app` — «open the Spotify app» — with that app open: the
placement kept every computer on the page player. The word «list» never reached the door, the music card never opened
on its own, and «not this one» had nothing to pick from.

Two players, whatever the screen: the provider's app with the asking screen, else our page player. The kind he names
travels to the media door. A request said to the agent opens the card on its search and leaves there the numbered
candidates with their owners; `play_result` picks one by number, name or owner.
The Spotify Web API is faked; nothing reaches the network.
Disarm: `_choose` keeping the page on a computer → the first two tests go red (`needs_app` again).
"""
from __future__ import annotations

import importlib

import pytest

from connectors import music
from connectors.music import registry
from connectors.music import youtube_audio as yta
from connectors.spotify import client

sp_provider = importlib.import_module("connectors.spotify.provider")

DESK = "desktop:96a57a44"
MAC = {"id": "mac-1", "is_active": False, "is_restricted": False, "name": "MacBook Pro", "type": "Computer"}
SPEAKER = {"id": "spk-1", "is_active": False, "is_restricted": False, "name": "Kitchen", "type": "Speaker"}

SHOW = {"id": "sh1", "uri": "spotify:show:sh1", "name": "Sueñacuentos", "publisher": None, "total_episodes": 115,
        "images": []}
LISTS = [{"id": f"pl{i}", "uri": f"spotify:playlist:pl{i}", "name": name, "owner": {"display_name": owner},
          "tracks": {"total": 20}, "images": []}
         for i, (name, owner) in enumerate([("Sueñacuentos", "♡KUROMI♡"), ("Sueñacuentos favoritos", "irene"),
                                            ("SUEÑA CUENTOS", "miku"), ("MAX Sueñacuentos", "jolaraka")], 1)]
EPISODES = [{"id": "e1", "uri": "spotify:episode:e1", "name": "El dragón que no sabía volar", "duration_ms": 600000}]
SONGS = [{"id": f"s{i}", "uri": f"spotify:track:s{i}", "name": n, "artists": [{"name": "Tradicional"}]}
         for i, n in enumerate(["Nana del caballo", "Duérmete niño"], 1)]


@pytest.fixture
def world(monkeypatch, tmp_path):
    import widgets.store as store
    from voice import screens
    monkeypatch.setattr(store, "_path", lambda wid: str(tmp_path / f"{wid}.json"))
    monkeypatch.setattr(store, "_legacy_path", lambda wid: str(tmp_path / f"{wid}_legacy.json"))
    monkeypatch.setattr(sp_provider, "_SETTLE_S", 0)
    monkeypatch.setattr(sp_provider.SpotifyProvider, "connected", lambda self: True)
    calls = {"played": [], "page": []}
    state = {"devices": [SPEAKER, MAC], "sounding": None}
    monkeypatch.setattr(yta, "_resolve", lambda q: (calls["page"].append(q), ("vid0000001", q))[1])

    def _search(q, types="track", limit=5):
        return {"tracks": {"items": []}, "shows": {"items": [SHOW]}, "playlists": {"items": LISTS},
                "albums": {"items": []}, "artists": {"items": []}}
    monkeypatch.setattr(client, "search", _search)
    monkeypatch.setattr(client, "devices", lambda: list(state["devices"]))

    def _play(uris=None, context_uri="", device_id=""):
        calls["played"].append({"context_uri": context_uri, "uris": uris, "device_id": device_id})
        dev = next((d for d in state["devices"] if d["id"] == device_id), None)
        state["sounding"] = dev
        return {}
    monkeypatch.setattr(client, "play", _play)
    monkeypatch.setattr(client, "pause", lambda device_id="": {})
    monkeypatch.setattr(client, "playback_state", lambda: (
        {"is_playing": True, "item": None, "device": {"id": state["sounding"]["id"], "name": state["sounding"]["name"]}}
        if state["sounding"] else {}))
    monkeypatch.setattr(client, "playlist", lambda pid: next(dict(p) for p in LISTS if p["id"] == pid))
    monkeypatch.setattr(client, "playlist_items", lambda pid, limit=50: [{"track": s} for s in SONGS])
    monkeypatch.setattr(client, "show", lambda sid: {**SHOW, "episodes": {"items": EPISODES}})
    registry._PROVIDERS.clear()
    registry._loaded = True
    registry.register(sp_provider.SpotifyProvider())
    registry.register(yta.YouTubeAudioProvider())
    screens._reset_for_tests()
    screens.begin_turn(DESK, "T87")
    yield calls, state
    screens._reset_for_tests()
    registry._PROVIDERS.clear()
    registry._loaded = False


def test_the_list_he_names_plays_on_the_spotify_of_this_computer(world):
    calls, _ = world
    r = music.control("play", "Sueñacuentos", kind="list")
    assert r.ok, r
    assert calls["played"] == [{"context_uri": "spotify:playlist:pl1", "uris": None, "device_id": "mac-1"}]
    assert calls["page"] == [], "nothing sounded on the page as well"
    found = r.extra["found"]
    assert found["chosen"] == "spotify:playlist:pl1" and len(found["candidates"]) == 5


def test_with_no_kind_named_the_podcast_of_that_name_plays_there_too_never_needs_app(world):
    calls, _ = world
    r = music.control("play", "Sueñacuentos")
    assert r.ok and r.reason != "needs_app", r
    assert calls["played"][0]["context_uri"] == "spotify:show:sh1" and calls["played"][0]["device_id"] == "mac-1"


def test_without_a_spotify_app_on_this_computer_a_list_of_songs_plays_on_our_page(world):
    calls, state = world
    state["devices"] = [SPEAKER]                       # Spotify only on a speaker elsewhere: never used
    r = music.control("play", "Sueñacuentos", kind="list")
    assert r.ok, r
    assert calls["played"] == [] and calls["page"] and "Nana del caballo" in calls["page"][0]


def test_the_card_opens_on_his_search_and_keeps_the_numbered_candidates_with_their_owners(world):
    from widgets.musica import browse, digest
    from widgets.musica import data as _md
    browse.begin_search("Sueñacuentos")
    db = _md._load_db()
    assert db["view"]["kind"] == "search" and db["browse"]["search"] == {"query": "Sueñacuentos", "pending": True}
    r = music.control("play", "Sueñacuentos", kind="list")
    browse.after_play("Sueñacuentos", r)
    db = _md._load_db()
    assert db["view"]["kind"] == "album", "the list that sounds opens on its page"
    assert [t["title"] for t in db["browse"]["album"]["tracks"]] == ["Nana del caballo", "Duérmete niño"]
    block = "\n".join(digest._found_lines(db))
    assert "1. podcast «Sueñacuentos»" in block
    assert "2. ▶ list «Sueñacuentos» — ♡KUROMI♡" in block and "4. list «Sueñacuentos favoritos» — irene" in block
    assert "play_result" in block


def test_not_this_one_picks_another_by_its_owner_and_it_plays_there(world):
    calls, _ = world
    from widgets.musica import browse
    from widgets.musica import data as _md
    browse.begin_search("Sueñacuentos")
    browse.after_play("Sueñacuentos", music.control("play", "Sueñacuentos", kind="list"))
    out = browse.a_play_result("play_result", {"item": "irene"})
    assert out["ok"] and out["position"] == 4 and out["owner"] == "irene", out
    assert calls["played"][-1] == {"context_uri": "spotify:playlist:pl2", "uris": None, "device_id": "mac-1"}
    assert _md._load_db()["browse"]["search"]["chosen"] == "spotify:playlist:pl2"
    by_number = browse.a_play_result("play_result", {"item": 1})
    assert by_number["ok"] and calls["played"][-1]["context_uri"] == "spotify:show:sh1"


def test_two_rows_carrying_his_words_are_asked_never_guessed(world):
    from widgets.musica import browse
    browse.after_play("Sueñacuentos", music.control("play", "Sueñacuentos", kind="list"))
    out = browse.a_play_result("play_result", {"item": "sueñacuentos"})
    assert not out["ok"] and out["error"] == "item_not_found" and len(out["options"]) == 5


def test_the_kind_he_names_rides_the_tool_call_to_the_music_lane():
    from nucleo.flash.tool_executor_calls import _t_play_music
    req = {"v": None}
    _t_play_music(args={"query": "Sueñacuentos", "kind": "list"}, music_req=req)
    assert req["v"] == {"query": "Sueñacuentos", "action": "play", "kind": "list"}


def test_an_episode_that_sounds_is_read_with_its_show(monkeypatch):
    """Measured live: the list of episodes sounded on the Mac and the player read nothing — Spotify only describes an
    episode when it is asked for (`additional_types`)."""
    asked = {}

    def _request(method, path, params=None, **_k):
        asked.update(params or {})
        return {"is_playing": True, "currently_playing_type": "episode", "device": {"id": "mac-1", "name": "MacBook Pro"},
                "item": {"type": "episode", "id": "e9", "uri": "spotify:episode:e9", "name": "Polvo de hada",
                         "duration_ms": 500000, "show": {"name": "Sueñacuentos", "images": []}}}
    monkeypatch.setattr(client, "_request", _request)
    np = sp_provider.SpotifyProvider().now_playing()
    assert "episode" in asked.get("additional_types", "")
    assert np.track is not None and np.track.title == "Polvo de hada" and np.track.artist == "Sueñacuentos"
