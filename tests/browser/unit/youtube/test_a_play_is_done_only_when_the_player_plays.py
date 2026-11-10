"""A play is done only when OUR player plays it: a new video, no player error, playing (four principles, P2).

V2-873: «new video» and «playing» are what the PLAYER reports (`player_state`, from its own onStateChange), never the
order: `videoId`/`paused` are written by the order, and «Hecho» was said over a video the player never changed. The
order alone meets nothing; the player's report does.

The old end state of `load`/`next` was «videoId changed» alone: a video the embedded player then refused (error 150,
«This video is unavailable») read as delivered. The manifest now declares the real outcome on our side, and every
field it names is a VALUE in the view (a missing key reads «unverifiable», never unmet — so an old store without
`src` must still show `src: ""`).
"""
from __future__ import annotations

import copy
import io
import json
import urllib.request

import pytest

from nucleo.circuit import baseline, verify
from widgets import store
from widgets.youtube import data as yt

_V1, _V2, _V3 = "dQw4w9WgXcQ", "9bZkp7q19f0", "kJQP7kiw5Fk"
_MANIFEST = json.load(open(yt.__file__.replace("data.py", "manifest.json"), encoding="utf-8"))


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=6: io.BytesIO(
        json.dumps({"title": "Vídeo", "author_name": "Canal"}).encode()))


def _dw(action: str):
    dw = copy.deepcopy(_MANIFEST["actions"][action]["done_when"])
    baseline.snapshot(dw)
    return dw


def _playing(vid: str = _V1, **extra):
    """The store as the player last REPORTED it: video `vid` loaded and playing."""
    db = yt._load()
    db.update({"videoId": vid, "playing_id": vid, "playing": True, "paused": False, "player_error": "",
               "list": [{"videoId": _V1, "title": "uno"}, {"videoId": _V2, "title": "dos"},
                        {"videoId": _V3, "title": "tres"}], "pos": 0, **extra})
    store.save("youtube", db)


def _patch(**fields):
    db = yt._load()
    db.update(fields)
    store.save("youtube", db)


def _player_reports(playing: bool):
    return yt.apply_action("player_state", {"playing": playing, "videoId": yt._load().get("videoId")})


def test_every_field_the_play_end_states_name_is_a_value_in_the_view():
    store.save("youtube", {"videoId": ""})          # an old store: no player_error, no playing, no src
    view = yt.view_data()
    for field in ("videoId", "player_error", "playing", "playing_id", "src"):
        assert field in view, f"`{field}` missing from the view: its clause would read unverifiable"


@pytest.mark.parametrize("action,payload", [
    ("load", {"videoId": _V2}), ("next", {}), ("play_item", {"item": "3"})])
def test_the_order_alone_meets_nothing_the_player_report_does(action, payload):
    _playing()
    dw = _dw(action)
    assert verify.check(dw) is False, "nothing happened yet: unmet"
    assert yt.apply_action(action, payload).get("ok")
    assert verify.check(dw) is False, "the ORDER changed the store, the player has not played it (V2-873)"
    assert _player_reports(True).get("playing") is True
    assert verify.check(dw) is True


def test_a_report_about_the_old_video_is_stale():
    _playing()
    dw = _dw("next")
    yt.apply_action("next", {})
    assert yt.apply_action("player_state", {"playing": True, "videoId": _V1}).get("stale")
    assert verify.check(dw) is False


@pytest.mark.parametrize("action", ["load", "next", "play_item", "play_result"])
def test_a_video_the_player_refused_is_not_done(action):
    _playing()
    dw = _dw(action)
    _patch(videoId=_V2, playing_id=_V2, playing=True, player_error="150")
    assert verify.check(dw) is False, "the player reported an error: the video is not playing"
    _patch(player_error="")
    assert verify.check(dw) is True


@pytest.mark.parametrize("action", ["load", "next", "play_item", "play_result", "play", "previous"])
def test_a_paused_player_is_not_playing(action):
    _playing(playing=False, paused=True)
    dw = _dw(action)
    _patch(videoId=_V2, playing_id=_V2, playing=False)
    assert verify.check(dw) is False


def test_play_pause_and_previous_are_done_when_the_player_says_so():
    _playing(playing=False, paused=True)
    dw_play = _dw("play")
    assert yt.apply_action("play", {}).get("ok")
    assert verify.check(dw_play) is False, "the order said play; the player has not"
    _player_reports(True)
    assert verify.check(dw_play) is True
    dw_pause = _dw("pause")
    assert yt.apply_action("pause", {}).get("ok")
    assert verify.check(dw_pause) is False
    _player_reports(False)
    assert verify.check(dw_pause) is True
    _playing(pos=1, videoId=_V2, playing=False, paused=True)
    dw_prev = _dw("previous")
    assert yt.apply_action("previous", {}).get("ok")
    _player_reports(True)
    assert verify.check(dw_prev) is True


@pytest.mark.parametrize("action", ["play_local", "play_torrent"])
def test_a_stream_is_done_when_its_src_changed_and_it_plays(action):
    _playing()
    dw = _dw(action)
    assert verify.check(dw) is False
    _patch(src="http://127.0.0.1/stream/abc", source="local", videoId="", paused=False)
    assert verify.check(dw) is True


def test_the_report_is_declared_as_internal():
    assert _MANIFEST["actions"]["player_state"]["desc"].startswith("Internal:")
    assert _MANIFEST["actions"]["player_state"].get("internal") is True


def test_a_stream_of_ours_is_named_by_its_source_when_it_plays():
    """V2-873 — a library or torrent row has no videoId; its own <video> reports what it plays too, and the report
    names the row by its source, so a start of one of our streams reads met only when it plays."""
    _playing()
    _patch(videoId="", src="/api/library/stream/a.mp4", playing_id="", playing=False)
    yt.apply_action("player_state", {"playing": True, "videoId": ""})
    db = yt._load()
    assert db["playing_id"] == "/api/library/stream/a.mp4" and db["playing"] is True
