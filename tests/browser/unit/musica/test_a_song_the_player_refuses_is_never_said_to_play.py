"""A song the page player REFUSES is never said to play — the next one his words find plays instead (V2-873, node 4.440).

Demo pass 2026-11-10: «pon algo de rosalía» resolved to «ROSALÍA - DESPECHÁ (Official Audio)», the page player answered
the IFrame API's `onError` 150 (its owner refuses embedding) and nothing sounded, while the card declared the song
playing and the agent said «Te pongo Rosalía». The card listened to the player's sound, never to its refusal.

Now the card reports the refusal (`player_error`, from `onError`), the song joins `yt.refused` and no lookup offers it
again, a song WE picked for his words is replaced by the next one those words find, and with no other the store keeps
`player_error`: «what sounds here» is empty (the end state of every start reads unmet) and the brain's digest says it.
What sounds here is what the page player REPORTS through the state door (V2-884 step 2), never the song picked.
"""
from __future__ import annotations

import pytest

from widgets.musica import data as md

from tests.browser.unit.musica.page_player import page_player

from tests.browser.unit.musica.test_a_silent_page_player_says_so_and_offers_the_tap import (  # noqa: F401
    _data, _mount, _page)

_DEAD, _NEXT = "DEADAUDIO01", "LIVEVIDEO01"


@pytest.fixture
def store_tmp(monkeypatch, tmp_path):
    import widgets.store as store
    from connectors.spotify import auth
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))   # the store's own layout: `has_state` reads it too
    monkeypatch.setattr(auth, "status", lambda: {"logged_in": False, "can_connect": True})
    store.save("musica", {"yt": {"videoId": _DEAD, "title": "Song (Official Audio)", "query": "some artist",
                                 "paused": False, "cmd_seq": 3, "volume": 70},
                          "source": {"provider": "youtube", "screen": "desktop:aa11"}})
    asked: list = []

    def resolve(query, skip=()):
        asked.append((query, tuple(skip)))
        return next(((v, f"title of {v}", "found") for v in (_DEAD, _NEXT) if v not in skip), ("", "", "empty"))
    monkeypatch.setattr("connectors.music.youtube_resolve._resolve", resolve)
    return asked


def _here():
    return md._live_fields(md._load_db())["here"]


def test_our_pick_refused_is_replaced_by_the_next_his_words_find(store_tmp):
    assert not _here()["title"], "the pick alone sounds nothing: only the page player's report does"
    r = md.apply_action("player_error", {"code": "150", "videoId": _DEAD})
    yt = md._load_db()["yt"]
    assert r["swapped_to"] == _NEXT and yt["videoId"] == _NEXT and not yt["player_error"]
    assert store_tmp == [("some artist", (_DEAD,))], "the refused song is skipped by the lookup itself"
    assert _DEAD in yt["refused"]


def test_with_no_other_song_nothing_is_said_to_sound(store_tmp, monkeypatch):
    monkeypatch.setattr("connectors.music.youtube_resolve._resolve", lambda q, skip=(): ("", "", "empty"))
    md.apply_action("player_error", {"code": "150", "videoId": _DEAD})
    assert md._load_db()["yt"]["player_error"] == "150"
    assert _here() == {"title": "", "source": ""}, "a refused song is not what sounds here: every start reads unmet"
    assert "REFUSED" in md.prompt_digest(), "the brain must not say «it's playing» over a refusal"


def test_a_late_report_about_a_replaced_song_only_blocks_it(store_tmp):
    r = md.apply_action("player_error", {"code": "101", "videoId": "OLDSONG0001"})
    yt = md._load_db()["yt"]
    assert r.get("stale") and yt["videoId"] == _DEAD and "OLDSONG0001" in yt["refused"]


def test_a_non_fatal_code_swaps_nothing(store_tmp):
    md.apply_action("player_error", {"code": "999", "videoId": _DEAD})
    assert md._load_db()["yt"]["videoId"] == _DEAD and not store_tmp


def test_the_card_reports_the_players_refusal_once(_page):
    _mount(_page, _data(videoId=_DEAD))
    for _ in range(3):
        _page.evaluate("() => window.dispatchEvent(new MessageEvent('message', {data: JSON.stringify("
                       "{event: 'onError', id: 'hb-musica', info: 150})}))")
    _page.evaluate("() => window.dispatchEvent(new MessageEvent('message', {data: JSON.stringify("
                   "{event: 'onError', id: 'hb-youtube', info: 150})}))")
    reports = [c[1] for c in _page.evaluate("() => window.__calls") if c[0] == "player_error"]
    assert reports == [{"code": "150", "videoId": _DEAD}], reports


@pytest.mark.parametrize("query", ["algo de rosalía", "some madonna"])
def test_what_sounds_here_is_what_the_page_player_says_it_plays(store_tmp, monkeypatch, query):
    """V2-873 — the end state of every start reads `here.title CHANGED`: it was written from the song PICKED, so a
    refused «Official Audio» read as sounding. Now only what the page player REPORTS through the state door (it plays,
    not silent, THIS song — V2-884 step 2) makes it sound here."""
    db = md._load_db()
    db["yt"]["query"] = query
    md._persist(db)
    assert not _here()["title"], "picked, not reported: nothing sounds"
    says = page_player(monkeypatch, "desktop:aa11")
    says(playing=True, playing_id="OTHERVID001", muted=False)
    assert not _here()["title"], "a report about another song is not this one sounding"
    says(playing_id=_DEAD)
    assert _here()["source"] == "youtube" and _here()["title"].startswith("Song")


def test_a_spotify_device_reads_as_before_and_a_library_file_sounds_when_its_audio_says_so(store_tmp, monkeypatch):
    """The scope: a Spotify device is the provider's own reading; a library file sounds when the page's <audio> says
    it plays — the same report as the embed's (V2-884 step 2)."""
    import widgets.store as store
    store.save("musica", {"yt": {}, "source": {"provider": "spotify", "device_id": "phone", "live": True}})
    monkeypatch.setattr("connectors.spotify.auth.status", lambda: {"logged_in": True, "can_connect": True})
    monkeypatch.setattr(md, "_now_playing", lambda: {"playing": True, "title": "Despechá", "device": "phone",
                                                     "device_id": "phone", "provider": "spotify"})
    assert _here() == {"title": "Despechá", "source": "spotify"}
    store.save("musica", {"yt": {}, "local": {"src": "/api/library/a.mp3", "title": "A song", "paused": False, "seq": 1}})
    monkeypatch.setattr(md, "_now_playing", lambda: None)
    live = md._live_fields(md._load_db())
    assert live["mode"] == "local" and live["here"]["title"] == "", "a file picked is not a file heard"
    page_player(monkeypatch, "desktop:aa11")(playing=True, muted=False)
    assert md._live_fields(md._load_db())["here"] == {"title": "A song", "source": "local"}


def test_the_card_says_the_song_the_player_plays(_page):
    _mount(_page, _data(videoId=_NEXT))
    _page.evaluate("() => window.dispatchEvent(new MessageEvent('message', {data: JSON.stringify("
                   "{event: 'infoDelivery', id: 'hb-musica', info: {playerState: 1, muted: false, "
                   "videoData: {video_id: '%s'}}})}))" % _NEXT)
    _page.wait_for_timeout(50)
    said = _page.evaluate("() => window.__states")[-1][0]
    assert said == {"playing": True, "muted": False, "playing_id": _NEXT}, said
    assert not [c for c in _page.evaluate("() => window.__calls") if c[0] == "player_audio"]


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_silence_of_a_refused_song_is_not_told_as_a_blocked_browser(store_tmp, monkeypatch, lang):
    """V2-873 — after the last refusal the page reports silence; «tap the card for sound» was told over it, a wrong
    reason (the owner refused the video, the browser did nothing)."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    monkeypatch.setattr("connectors.music.youtube_resolve._resolve", lambda q, skip=(): ("", "", "empty"))
    md.apply_action("player_error", {"code": "150", "videoId": _DEAD})
    got = page_player(monkeypatch, "desktop:aa11")(muted=True, playing=False, playing_id=_DEAD)
    assert got["facts"] == [] and not got.get("_on"), got   # no fact turns on: no tell is armed
