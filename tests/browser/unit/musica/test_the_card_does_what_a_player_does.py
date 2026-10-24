"""V2-795 — the music card does what a player does: list management, the queue, play modes, mute, search and the
catalogue pages, each a DECLARED op reached through the generic widget door.

Providers are fakes registered in the real registry's place; the catalogue is a fake too. Nothing reaches the
network and nothing touches the operator's store (the store is redirected to a temp dir).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from connectors.music import base as mb
from widgets.musica import data as md

ROOT = Path(__file__).resolve().parents[4]


class _Prov(mb.MusicProvider):
    """A provider that records what it is asked and keeps a queue of its own."""

    def __init__(self, name="youtube", editable=True):
        self.name, self.editable = name, editable
        self.calls: list = []
        self.shuffle, self.repeat, self.volume = False, "off", 70

    def connected(self): return True
    def search(self, query, limit=5): return [mb.Track(title=query, uri=f"{self.name}:{query}")]

    def play(self, query="", uri=""):
        self.calls.append(("play", query, uri))
        return mb.MusicResult(ok=True, provider=self.name, action="play")

    def enqueue(self, query="", uri=""):
        self.calls.append(("queue", query, uri))
        return mb.MusicResult(ok=True, provider=self.name, action="queue")

    def pause(self): return mb.MusicResult(ok=True)
    def resume(self): return mb.MusicResult(ok=True)
    def next(self): return mb.MusicResult(ok=True)
    def previous(self): return mb.MusicResult(ok=True)

    def set_volume(self, percent):
        self.volume = percent
        self.calls.append(("volume", percent))
        return mb.MusicResult(ok=True, provider=self.name, action="volume")

    def now_playing(self): return mb.NowPlaying(playing=True, volume=self.volume, provider=self.name)

    def set_shuffle(self, on):
        self.shuffle = on
        return mb.MusicResult(ok=True, provider=self.name, action="shuffle")

    def set_repeat(self, mode):
        self.repeat = mode
        return mb.MusicResult(ok=True, provider=self.name, action="repeat")

    # the free player's queue lives in the card's store — the fake edits it THERE, like the real one
    @property
    def queue(self):
        return list((md._load_db().get("yt") or {}).get("queue") or [])

    @queue.setter
    def queue(self, items):
        db = md._load_db()
        db["yt"] = {**(db.get("yt") or {}), "queue": list(items)}
        md._persist(db)

    def queue_items(self): return [mb.Track(title=q) for q in self.queue]

    def queue_edit(self, op, index=-1, to=-1):
        if not self.editable:
            return super().queue_edit(op, index, to)
        q = self.queue
        if op == "clear":
            q = []
        else:
            item = q.pop(index)
            if op == "move":
                q.insert(to, item)
        self.queue = q
        return mb.MusicResult(ok=True, provider=self.name, action="queue_" + op)

    def play_context(self, uri, label=""):
        self.calls.append(("context", uri))
        return mb.MusicResult(ok=uri.startswith(self.name + ":"), provider=self.name, reason="unsupported")


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    import widgets.store as store
    from connectors.spotify import auth
    monkeypatch.setattr(store, "_path", lambda wid: str(tmp_path / f"{wid}.json"))
    monkeypatch.setattr(store, "_legacy_path", lambda wid: str(tmp_path / f"{wid}_legacy.json"))
    monkeypatch.setattr(auth, "status", lambda: {"logged_in": False, "can_connect": True})


@pytest.fixture
def prov(monkeypatch):
    from connectors.music import registry
    p = _Prov()
    monkeypatch.setattr(registry, "available", lambda: [p])
    return p


def _seed(**db):
    import widgets.store as store
    store.save("musica", db)


def _list(name, *titles):
    return {"id": name.lower(), "name": name, "art": "",
            "tracks": [{"title": t, "artist": "X", "query": f"{t} X", "uri": "", "art": ""} for t in titles]}


# ── list management ───────────────────────────────────────────────────────────────────────────────────────

def test_a_list_is_renamed_by_its_spoken_name():
    _seed(playlists=[_list("Rock", "A")])
    r = md.apply_action("rename_playlist", {"playlist": "rock", "name": "Rock de los 80"})
    assert r["ok"] and r["name"] == "Rock de los 80"
    assert [p["name"] for p in md._load_db()["playlists"]] == ["Rock de los 80"]


def test_deleting_a_list_takes_it_away_and_leaves_its_screen():
    _seed(playlists=[_list("Rock", "A", "B"), _list("Jazz", "C")], view={"kind": "playlist", "id": "rock"})
    r = md.apply_action("delete_playlist", {"playlist": "Rock"})
    assert r["ok"] and r["tracks"] == 2
    db = md._load_db()
    assert [p["name"] for p in db["playlists"]] == ["Jazz"] and db["view"]["kind"] == "library"


def test_a_missing_list_is_refused_naming_the_ones_that_exist():
    _seed(playlists=[_list("Jazz", "C")])
    for op in ("rename_playlist", "delete_playlist", "move_track"):
        r = md.apply_action(op, {"playlist": "Salsa", "name": "x", "item": "1", "to": "1"})
        assert not r["ok"] and "Jazz" in r["message"], op


def test_a_song_moves_inside_its_list_by_number_or_by_name():
    _seed(playlists=[_list("Rock", "A", "B", "C")])
    assert md.apply_action("move_track", {"playlist": "Rock", "item": "3", "to": "1"})["position"] == 1
    assert [t["title"] for t in md._load_db()["playlists"][0]["tracks"]] == ["C", "A", "B"]
    md.apply_action("move_track", {"playlist": "Rock", "item": "C", "to": "3"})
    assert [t["title"] for t in md._load_db()["playlists"][0]["tracks"]] == ["A", "B", "C"]


def test_a_list_plays_from_the_song_he_points_at(prov):
    _seed(playlists=[_list("Rock", "A", "B", "C")])
    assert md.apply_action("play_playlist", {"playlist": "Rock", "from": "2"})["ok"]
    assert [c[1] for c in prov.calls] == ["B X", "C X"], "B now, the rest queued — A is behind the start"


def test_a_shuffled_list_keeps_every_song(prov, monkeypatch):
    import random
    monkeypatch.setattr(random, "shuffle", lambda xs: xs.reverse())
    _seed(playlists=[_list("Rock", "A", "B", "C")])
    md.apply_action("play_playlist", {"playlist": "Rock", "shuffle": True})
    assert [c[1] for c in prov.calls] == ["C X", "B X", "A X"]


# ── the queue, the modes, the volume ─────────────────────────────────────────────────────────────────────

def test_the_card_shows_the_free_players_queue_with_what_it_knows_of_each_song(prov):
    _seed(yt={"videoId": "v1", "title": "Now", "queue": ["A X", "zzz"]}, playlists=[_list("Rock", "A")])
    q = md.view_data()["queue"]
    assert q["editable"] and q["source"] == "youtube"
    assert [(i["title"], i["artist"]) for i in q["items"]] == [("A", "X"), ("zzz", "")]


def test_the_queue_is_edited_through_the_provider(prov):
    _seed(yt={"videoId": "v1", "queue": ["Song A", "Song B", "Song C"]})
    assert md.apply_action("queue_remove", {"item": "2"})["ok"] and prov.queue == ["Song A", "Song C"]
    assert md.apply_action("queue_move", {"item": "Song C", "to": "1"})["ok"] and prov.queue == ["Song C", "Song A"]
    assert md.apply_action("queue_clear", {})["ok"] and prov.queue == []


def test_a_queue_the_provider_cannot_edit_says_so(prov):
    prov.editable = False
    _seed(yt={"videoId": "v1", "queue": ["Song A"]})
    r = md.apply_action("queue_remove", {"item": "1"})
    assert not r["ok"] and r["reason"] == "unsupported" and "edited" in r["message"]


def test_a_song_not_in_the_queue_is_refused_naming_whats_next(prov):
    _seed(yt={"videoId": "v1", "queue": ["Song A"]})
    r = md.apply_action("queue_remove", {"item": "Nope"})
    assert not r["ok"] and "Song A" in r["message"]


def test_shuffle_and_repeat_reach_the_player_and_the_card_shows_them(prov):
    assert md.apply_action("shuffle", {"on": True})["ok"] and prov.shuffle is True
    assert md.apply_action("repeat", {"mode": "one"})["ok"] and prov.repeat == "one"
    _seed(yt={"videoId": "v1", "shuffle": True, "repeat": "all"})
    assert md.view_data()["modes"] == {"shuffle": True, "repeat": "all", "supported": True}


def test_repeat_without_a_mode_is_the_next_step_of_the_cycle(prov):
    _seed(yt={"videoId": "v1", "repeat": "all"})
    assert md.apply_action("repeat", {})["repeat"] == "one"


def test_mute_remembers_the_level_and_gives_it_back(prov):
    _seed(yt={"videoId": "v1", "volume": 42})
    assert md.apply_action("set_volume", {"mute": True})["ok"]
    assert prov.calls[-1] == ("volume", 0) and md._load_db()["mute_restore"] == 42
    md.apply_action("set_volume", {"mute": False})
    assert prov.calls[-1] == ("volume", 42)


# ── what the card saw playing ────────────────────────────────────────────────────────────────────────────

def test_a_song_the_card_sees_playing_lands_in_recent_once():
    assert md.apply_action("played", {"title": "Hey Jude", "artist": "The Beatles"})["counted"]
    assert not md.apply_action("played", {"title": "Hey Jude", "artist": "The Beatles"})["counted"], \
        "a re-render or a reload is not a second play"
    db = md._load_db()
    assert db["recent"][0]["title"] == "Hey Jude" and list(db["counts"].values())[0]["count"] == 1


# ── the catalogue ────────────────────────────────────────────────────────────────────────────────────────

_FAKE_SEARCH = {"query": "queen", "source": "itunes",
                "tracks": [{"title": "Bohemian Rhapsody", "artist": "Queen", "uri": ""}],
                "artists": [{"id": "1", "name": "Queen", "source": "itunes"}],
                "albums": [{"id": "9", "name": "A Night at the Opera", "artist": "Queen", "source": "itunes"}],
                "playlists": []}
_FAKE_ALBUM = {"album": {"id": "9", "name": "A Night at the Opera", "artist": "Queen", "uri": "", "source": "itunes"},
               "tracks": [{"title": "Death on Two Legs", "artist": "Queen", "query": "Death on Two Legs Queen"},
                          {"title": "Bohemian Rhapsody", "artist": "Queen", "query": "Bohemian Rhapsody Queen"}]}


@pytest.fixture
def cat(monkeypatch):
    from connectors.music import catalog
    asked = []
    monkeypatch.setattr(catalog, "search", lambda q, limit=8: (asked.append(("search", q)), _FAKE_SEARCH)[1])
    monkeypatch.setattr(catalog, "album", lambda ref: (asked.append(("album", ref)), _FAKE_ALBUM)[1])
    monkeypatch.setattr(catalog, "artist", lambda ref: (asked.append(("artist", ref)), {
        "artist": {"id": "1", "name": "Queen", "source": "itunes"}, "top": _FAKE_ALBUM["tracks"], "albums": []})[1])
    return asked


def test_a_search_is_kept_for_the_card_and_named_for_the_turn(cat):
    r = md.apply_action("search", {"query": "queen"})
    assert r["ok"] and r["tracks"] == 1 and r["artists"] == 1 and r["top"] == ["Bohemian Rhapsody — Queen"]
    db = md._load_db()
    assert db["view"]["kind"] == "search" and db["browse"]["search"]["query"] == "queen"


def test_an_artist_and_an_album_open_as_pages(cat):
    assert md.apply_action("open_view", {"kind": "artist", "name": "Queen"})["view"]["kind"] == "artist"
    assert md._load_db()["browse"]["artist"]["artist"]["name"] == "Queen"
    assert md.apply_action("open_view", {"kind": "album", "id": "9", "source": "itunes"})["view"] == \
        {"kind": "album", "id": "9"}


def test_an_album_without_a_context_uri_plays_track_by_track(prov, cat):
    r = md.apply_action("play_album", {"album": "A Night at the Opera", "artist": "Queen"})
    assert r["ok"] and r["tracks"] == 2
    assert [c[:2] for c in prov.calls] == [("play", "Death on Two Legs Queen"), ("queue", "Bohemian Rhapsody Queen")]


def test_an_album_the_provider_knows_plays_as_one_context(prov, cat):
    r = md.apply_action("play_album", {"uri": "youtube:album:9", "album": "X"})
    assert r["ok"] and prov.calls == [("context", "youtube:album:9")]


def test_nothing_found_says_so():
    from connectors.music import catalog
    import unittest.mock as um
    with um.patch.object(catalog, "search", lambda q, limit=8: {"query": q, "tracks": [], "artists": [],
                                                                  "albums": [], "playlists": []}):
        r = md.apply_action("search", {"query": "zzzz"})
    assert r["ok"] and "Nothing found" in r["message"]


# ── declared, reachable, and paid for only once ──────────────────────────────────────────────────────────

NEW_OPS = {"rename_playlist", "delete_playlist", "move_track", "shuffle", "repeat", "queue_remove", "queue_move",
           "queue_clear", "search", "play_album"}


def test_every_new_op_is_declared_and_handled_and_the_cards_own_report_is_internal():
    man = json.loads((ROOT / "widgets/musica/manifest.json").read_text(encoding="utf-8"))
    acts = man["actions"]
    assert NEW_OPS <= set(acts) and NEW_OPS <= set(md.ACTIONS)
    assert set(acts) == set(md.ACTIONS), "declared == handled"
    assert acts["played"].get("internal") is True
    assert acts["delete_playlist"].get("confirm") is True and acts["delete_playlist"].get("confirm_q")
    assert acts["search"].get("view") is True


def test_the_model_is_offered_the_new_ops_and_never_the_internal_one():
    from widgets import brief
    row = next(ln for ln in brief.for_prompt(open_ids=["musica"]).splitlines() if ln.startswith("- musica "))
    for op in NEW_OPS:
        assert op in row, op
    assert "played" not in row and "enrich_art" not in row
