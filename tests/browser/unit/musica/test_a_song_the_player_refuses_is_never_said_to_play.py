"""A song the page player REFUSES is never said to play — the next one his words find plays instead (V2-873, node 4.440).

Demo pass 2026-11-10: «pon algo de rosalía» resolved to «ROSALÍA - DESPECHÁ (Official Audio)», the page player answered
the IFrame API's `onError` 150 (its owner refuses embedding) and nothing sounded, while the card declared the song
playing and the agent said «Te pongo Rosalía». The card listened to the player's sound, never to its refusal.

Now the card reports the refusal (`player_error`, from `onError`), the song joins `yt.refused` and no lookup offers it
again, a song WE picked for his words is replaced by the next one those words find, and with no other the store keeps
`player_error`: «what sounds here» is empty (the end state of every start reads unmet) and the brain's digest says it.
"""
from __future__ import annotations

import pytest

from widgets.musica import data as md

from tests.browser.unit.musica.test_a_silent_page_player_says_so_and_offers_the_tap import (  # noqa: F401
    _data, _mount, _page)

_DEAD, _NEXT = "DEADAUDIO01", "LIVEVIDEO01"


@pytest.fixture
def store_tmp(monkeypatch, tmp_path):
    import widgets.store as store
    from connectors.spotify import auth
    monkeypatch.setattr(store, "_path", lambda wid: str(tmp_path / f"{wid}.json"))
    monkeypatch.setattr(store, "_legacy_path", lambda wid: str(tmp_path / f"{wid}_legacy.json"))
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
    assert _here()["title"], "before the report the store believes it sounds"
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
