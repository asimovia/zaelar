"""The media door finds what can be PLAYED that his words name (V2-860 T2.1).

Measured on a phone (2026-11-07): «pon Sueña cuentos» played the first SONG the catalogue answered («Sueña», another
artist) while the podcast «Sueñacuentos» sat in the same answer. The door compares his words with the NAME of every
kind the catalogue knows — a string comparison against the catalogue's own answer, never a table of our words — and
tells the whole he named (podcast, list, album) from a song. Disarm: `named_whole` returning None → red.
"""
from __future__ import annotations

import pytest

from search import media as M
from search import find_media
from search.result import MODULES


def _answer(**kinds):
    base = {"source": "spotify", "tracks": [], "albums": [], "playlists": [], "shows": [], "artists": []}
    return {**base, **kinds}


PHONE = _answer(
    tracks=[{"title": "Sueña", "artist": "Luis Miguel", "uri": "spotify:track:1", "source": "spotify"},
            {"title": "Better With Time", "artist": "Emily", "uri": "spotify:track:2", "source": "spotify"}],
    shows=[{"name": "Sueñacuentos", "owner": "Elena Lostalé", "uri": "spotify:show:9", "source": "spotify"}],
    albums=[{"name": "Sueñacuentos Estudio", "artist": "Varios", "uri": "spotify:album:5", "source": "spotify"}])


@pytest.mark.parametrize("words", ["Sueña cuentos", "Sueñacuentos", "pon Sueñacuentos de Elena Lostalé",
                                   "the Sueñacuentos podcast"])
def test_the_podcast_his_words_name_beats_its_namesake_song(words):
    got = find_media(words, catalogue=lambda q: PHONE)
    whole = M.named_whole(words, got["candidates"])
    assert whole is not None and whole["kind"] == "show" and whole["uri"] == "spotify:show:9"


def test_spaces_aside_the_name_is_the_same_name():
    assert M.name_fit("Sueña cuentos", "Sueñacuentos") == 1.0
    assert M.name_fit("true blue", "True Blue") == 1.0
    assert 0 < M.name_fit("el podcast Sueñacuentos", "Sueñacuentos") < 1.0


def test_a_song_title_keeps_the_song_road():
    answer = _answer(tracks=[{"title": "True Blue", "artist": "Madonna", "uri": "spotify:track:7", "source": "spotify"}],
                     albums=[{"name": "True Blue", "artist": "Madonna", "uri": "spotify:album:7", "source": "spotify"}])
    got = find_media("True Blue", catalogue=lambda q: answer)
    assert got["candidates"][0]["kind"] == "track", "a song keeps the tie"
    assert M.named_whole("True Blue", got["candidates"]) is None


def test_an_album_named_with_its_artist_is_the_album():
    answer = _answer(tracks=[{"title": "Like a Prayer", "artist": "Madonna", "uri": "spotify:track:3", "source": "spotify"}],
                     albums=[{"name": "True Blue", "artist": "Madonna", "uri": "spotify:album:7", "source": "spotify"}])
    whole = M.named_whole("True Blue de Madonna", find_media("True Blue de Madonna", catalogue=lambda q: answer)["candidates"])
    assert whole is not None and whole["kind"] == "album"


def test_a_whole_without_a_uri_is_never_named():
    answer = _answer(shows=[{"name": "Sueñacuentos", "owner": "x", "uri": "", "source": "itunes"}])
    assert M.named_whole("Sueñacuentos", find_media("Sueñacuentos", catalogue=lambda q: answer)["candidates"]) is None


def test_video_ranks_by_name_and_music_falls_to_it_when_the_catalogue_is_empty(monkeypatch):
    from search import video
    vids = [{"videoId": "a" * 11, "title": "Cooking show live", "channel": "TV"},
            {"videoId": "b" * 11, "title": "Lofi beats to study", "channel": "Lofi"}]
    monkeypatch.setattr(video, "find_videos", lambda q, n=5, **k: list(vids))
    got = find_media("lofi beats", kind="video")
    assert got["source"] == "youtube" and got["candidates"][0]["video_id"] == "b" * 11
    fell = find_media("lofi beats", catalogue=lambda q: _answer())
    assert fell["source"] == "youtube" and fell["candidates"][0]["kind"] == "video"


def test_nothing_found_is_an_honest_empty(monkeypatch):
    from search import video
    monkeypatch.setattr(video, "find_videos", lambda q, n=5, **k: [])
    got = find_media("zzqx nothing", catalogue=lambda q: _answer())
    assert got["candidates"] == [] and M.named_whole("zzqx nothing", got["candidates"]) is None


def test_a_catalogue_that_raises_is_not_found_not_a_crash(monkeypatch):
    from search import video
    monkeypatch.setattr(video, "find_videos", lambda q, n=5, **k: [])
    def boom(q):
        raise RuntimeError("down")
    assert find_media("x", catalogue=boom)["candidates"] == []


def test_the_media_door_is_not_a_route_of_the_question_every_turn_asks():
    assert "media" not in MODULES


def test_a_public_candidate_carries_no_raw_row():
    c = find_media("Sueñacuentos", catalogue=lambda q: PHONE)["candidates"][0]
    assert "item" in c and "item" not in M.public(c)


def test_a_caller_that_only_asks_which_whole_pays_no_video_lookup(monkeypatch):
    from search import video
    asked = []
    monkeypatch.setattr(video, "find_videos", lambda q, n=5, **k: asked.append(q) or [])
    find_media("x", catalogue=lambda q: _answer(), video=False)
    assert asked == []
