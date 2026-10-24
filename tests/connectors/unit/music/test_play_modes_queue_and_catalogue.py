"""V2-795 — the music connector's half of «a player»: play modes and an editable queue on the free player, the same
contract over Spotify's API, and ONE catalogue door that prefers the connected account and falls back to the free
iTunes metadata. Store, HTTP and resolution are all faked; nothing reaches the network."""
from __future__ import annotations

import importlib

import pytest

import connectors.music.youtube_audio as ya
from connectors.music import base as mb, catalog, itunes


@pytest.fixture
def store(monkeypatch):
    db = {}
    monkeypatch.setattr(ya, "_load_yt", lambda: dict(db.get("yt") or {}))
    monkeypatch.setattr(ya, "_save_yt", lambda yt: db.__setitem__("yt", dict(yt)))
    monkeypatch.setattr(ya, "_resolve", lambda q: ("V" + q.replace(" ", "")[:10].ljust(10, "0"), q))
    return db


def _playing(store, query, queue=(), **modes):
    store["yt"] = {"videoId": "V" + query.replace(" ", "")[:10].ljust(10, "0"), "query": query, "title": query,
                   "cmd_seq": 1, "queue": list(queue), **modes}


# ── the free player: repeat, shuffle, the queue ──────────────────────────────────────────────────────────

def test_repeat_one_replays_the_same_video_from_the_top_without_reloading_it(store):
    _playing(store, "song a", ["song b"], repeat="one")
    vid = store["yt"]["videoId"]
    r = ya.YouTubeAudioProvider().on_ended()
    yt = store["yt"]
    assert r.ok and yt["videoId"] == vid and yt["seek"] == {"n": 1, "to": 0.0} and yt["queue"] == ["song b"]
    assert yt["cmd_seq"] == 2, "a play command, so a player that stopped at the end starts again"


def test_a_skip_under_repeat_one_is_still_a_skip(store):
    _playing(store, "song a", ["song b"], repeat="one")
    ya.YouTubeAudioProvider().next()
    assert store["yt"]["query"] == "song b"


def test_repeat_all_sends_the_finished_song_to_the_back_of_the_queue(store):
    _playing(store, "song a", ["song b"], repeat="all")
    ya.YouTubeAudioProvider().on_ended()
    assert store["yt"]["query"] == "song b" and store["yt"]["queue"] == ["song a"]


def test_without_repeat_an_empty_queue_ends_quietly(store):
    _playing(store, "song a")
    r = ya.YouTubeAudioProvider().on_ended()
    assert r.ok and r.reason == "empty_queue" and store["yt"]["query"] == "song a"


def test_shuffle_picks_the_next_song_at_random(store, monkeypatch):
    import random
    monkeypatch.setattr(random, "randrange", lambda n: n - 1)
    _playing(store, "song a", ["song b", "song c", "song d"], shuffle=True)
    ya.YouTubeAudioProvider().on_ended()
    assert store["yt"]["query"] == "song d" and store["yt"]["queue"] == ["song b", "song c"]


def test_the_modes_are_kept_without_touching_the_player(store):
    _playing(store, "song a")
    p = ya.YouTubeAudioProvider()
    assert p.set_shuffle(True).ok and p.set_repeat("all").ok
    assert store["yt"]["repeat"] == "all"
    assert p.set_repeat("bogus").ok, "an unknown mode is read as «off», never stored as given"
    yt = store["yt"]
    assert yt["shuffle"] is True and yt["repeat"] == "off" and yt["cmd_seq"] == 1
    np = p.now_playing()
    assert np.shuffle is True and np.repeat == "off"


def test_the_free_queue_can_be_seen_and_edited(store):
    _playing(store, "song a", ["b", "c", "d"])
    p = ya.YouTubeAudioProvider()
    assert [t.title for t in p.queue_items()] == ["b", "c", "d"]
    assert p.queue_edit("move", 2, 0).ok and store["yt"]["queue"] == ["d", "b", "c"]
    assert p.queue_edit("remove", 1).ok and store["yt"]["queue"] == ["d", "c"]
    assert not p.queue_edit("remove", 9).ok, "an index that names nothing is refused, not ignored"
    assert p.queue_edit("clear").ok and store["yt"]["queue"] == []
    assert store["yt"]["cmd_seq"] == 1, "editing the queue never touches the song that is playing"


def test_a_provider_without_these_says_unsupported():
    class Bare(mb.MusicProvider):
        name = "bare"
        def connected(self): return True
        def search(self, q, limit=5): return []
        def play(self, query="", uri=""): ...
        def pause(self): ...
        def resume(self): ...
        def next(self): ...
        def previous(self): ...
        def set_volume(self, p): ...
        def now_playing(self): ...
    b = Bare()
    assert b.set_shuffle(True).reason == "unsupported" and b.queue_edit("clear").reason == "unsupported"
    assert b.queue_items() is None and b.search_catalog("x") is None and b.play_context("x").ok is False


# ── Spotify: the same contract over its API ──────────────────────────────────────────────────────────────

def test_spotify_maps_the_repeat_words_and_reads_the_modes_back(monkeypatch):
    from connectors.spotify import client
    provider = importlib.import_module("connectors.spotify.provider")
    sent = []
    monkeypatch.setattr(client, "repeat", lambda state, device_id="": sent.append(("repeat", state)) or {})
    monkeypatch.setattr(client, "shuffle", lambda state, device_id="": sent.append(("shuffle", state)) or {})
    monkeypatch.setattr(client, "playback_state", lambda: {"is_playing": True, "shuffle_state": True,
                                                           "repeat_state": "track", "item": {"name": "S"}})
    p = provider.SpotifyProvider()
    assert p.set_repeat("all").ok and p.set_repeat("one").ok and p.set_shuffle(True).ok
    assert sent == [("repeat", "context"), ("repeat", "track"), ("shuffle", True)]
    np = p.now_playing()
    assert np.shuffle is True and np.repeat == "one"


def test_spotifys_queue_is_read_only(monkeypatch):
    from connectors.spotify import client
    provider = importlib.import_module("connectors.spotify.provider")
    monkeypatch.setattr(client, "queue", lambda: {"queue": [{"name": "Next", "uri": "spotify:track:1",
                                                             "artists": [{"name": "A"}]}]})
    p = provider.SpotifyProvider()
    assert [t.title for t in p.queue_items()] == ["Next"]
    assert p.queue_edit("remove", 0).reason == "unsupported", "the Web API cannot remove from its queue"


def test_spotify_catalogue_carries_its_own_uris(monkeypatch):
    from connectors.spotify import client
    provider = importlib.import_module("connectors.spotify.provider")
    monkeypatch.setattr(client, "search", lambda q, types="track", limit=5: {
        "tracks": {"items": [{"name": "T", "uri": "spotify:track:1", "artists": [{"name": "A"}]}]},
        "artists": {"items": [{"id": "a1", "name": "A", "uri": "spotify:artist:a1", "images": []}]},
        "albums": {"items": [{"id": "al1", "name": "Al", "uri": "spotify:album:al1", "release_date": "1999-01-01",
                              "artists": [{"name": "A"}]}]},
        "playlists": {"items": [None, {"id": "p1", "name": "P", "uri": "spotify:playlist:p1",
                                       "tracks": {"total": 7}, "owner": {"display_name": "O"}}]}})
    got = provider.SpotifyProvider().search_catalog("a")
    assert got["tracks"][0]["uri"] == "spotify:track:1" and got["tracks"][0]["provider"] == "spotify"
    assert got["albums"][0]["year"] == "1999" and got["playlists"][0]["count"] == 7


# ── the catalogue door ───────────────────────────────────────────────────────────────────────────────────

class _Cat(mb.MusicProvider):
    def __init__(self, name, answer=None):
        self.name, self.answer = name, answer
    def connected(self): return True
    def search(self, q, limit=5): return [mb.Track(title="plain " + q, uri=f"{self.name}:1")]
    def search_catalog(self, q, limit=8): return self.answer
    def play(self, query="", uri=""): ...
    def pause(self): ...
    def resume(self): ...
    def next(self): ...
    def previous(self): ...
    def set_volume(self, p): ...
    def now_playing(self): ...


def test_the_connected_accounts_catalogue_comes_first(monkeypatch):
    from connectors.music import registry
    monkeypatch.setattr(registry, "available", lambda: [_Cat("spotify", {"tracks": [{"title": "S"}]})])
    monkeypatch.setattr(itunes, "search", lambda q, limit=8: pytest.fail("the free catalogue is the fallback"))
    assert catalog.search("x")["source"] == "spotify"


def test_without_an_account_the_free_metadata_answers(monkeypatch):
    from connectors.music import registry
    monkeypatch.setattr(registry, "available", lambda: [_Cat("youtube")])
    monkeypatch.setattr(itunes, "search", lambda q, limit=8: {"tracks": [{"title": "I"}], "artists": [],
                                                             "albums": [], "playlists": []})
    assert catalog.search("x")["source"] == "itunes"


def test_with_nothing_else_a_search_is_never_emptier_than_a_play(monkeypatch):
    from connectors.music import registry
    monkeypatch.setattr(registry, "available", lambda: [_Cat("youtube")])
    monkeypatch.setattr(itunes, "search", lambda q, limit=8: {"tracks": [], "artists": [], "albums": [],
                                                             "playlists": []})
    got = catalog.search("x")
    assert got["source"] == "youtube" and got["tracks"][0]["title"] == "plain x"


def test_an_album_named_in_words_is_found_by_searching_it_first(monkeypatch):
    from connectors.music import registry
    monkeypatch.setattr(registry, "available", lambda: [])
    monkeypatch.setattr(itunes, "search", lambda q, limit=8: {
        "tracks": [], "artists": [], "playlists": [], "albums": [{"id": "77", "name": "Thriller", "source": "itunes"}]})
    monkeypatch.setattr(itunes, "album", lambda cid: {"album": {"id": cid}, "tracks": [{"title": "Beat It"}]})
    assert catalog.album({"name": "Thriller", "artist": "Michael Jackson"})["album"]["id"] == "77"


def test_itunes_rows_become_the_shared_shapes(monkeypatch):
    rows = {"song": [{"trackName": "T", "artistName": "A", "artistId": 5, "collectionName": "C",
                      "artworkUrl100": "https://x/100x100bb.jpg", "trackId": 1, "trackTimeMillis": 1000}],
            "musicArtist": [{"artistName": "A", "artistId": 5}],
            "album": [{"collectionName": "C", "collectionId": 9, "artistName": "A", "releaseDate": "2001-02-03"}]}
    monkeypatch.setattr(itunes, "_get", lambda path, params: rows[params["entity"]])
    got = itunes.search("a")
    t = got["tracks"][0]
    assert t["art"] == "https://x/600x600bb.jpg" and t["uri"] == "" and t["query"] == "T A"
    assert got["artists"][0]["art"] == "https://x/600x600bb.jpg", "an artist borrows the cover of one of its songs"
    assert got["albums"][0]["year"] == "2001"


def test_an_itunes_failure_is_empty_results_not_an_exception(monkeypatch):
    import urllib.request
    def boom(*a, **k):
        raise OSError("offline")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert itunes.search("a") == {"tracks": [], "artists": [], "albums": [], "playlists": []}
    assert itunes.album("12") is None and itunes.cover("t", "a") == ("", "")
