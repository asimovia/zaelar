"""A play is done only when OUR player plays it: a new video, no player error, not paused (four principles, P2).

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
    db = yt._load()
    db.update({"videoId": vid, "paused": False, "player_error": "",
               "list": [{"videoId": _V1, "title": "uno"}, {"videoId": _V2, "title": "dos"},
                        {"videoId": _V3, "title": "tres"}], "pos": 0, **extra})
    store.save("youtube", db)


def _patch(**fields):
    db = yt._load()
    db.update(fields)
    store.save("youtube", db)


def test_every_field_the_play_end_states_name_is_a_value_in_the_view():
    store.save("youtube", {"videoId": ""})          # an old store: no player_error, no paused, no src
    view = yt.view_data()
    for field in ("videoId", "player_error", "paused", "src"):
        assert field in view, f"`{field}` missing from the view: its clause would read unverifiable"


@pytest.mark.parametrize("action,payload", [
    ("load", {"videoId": _V2}), ("next", {}), ("play_item", {"item": "3"})])
def test_a_new_video_the_player_plays_meets_the_end_state(action, payload):
    _playing()
    dw = _dw(action)
    assert verify.check(dw) is False, "nothing happened yet: unmet"
    assert yt.apply_action(action, payload).get("ok")
    assert verify.check(dw) is True


@pytest.mark.parametrize("action", ["load", "next", "play_item", "play_result"])
def test_a_video_the_player_refused_is_not_done(action):
    _playing()
    dw = _dw(action)
    _patch(videoId=_V2, paused=False, player_error="150")
    assert verify.check(dw) is False, "the player reported an error: the video is not playing"
    _patch(player_error="")
    assert verify.check(dw) is True


@pytest.mark.parametrize("action", ["load", "next", "play_item", "play_result", "play", "previous"])
def test_a_paused_player_is_not_playing(action):
    _playing(paused=True)
    dw = _dw(action)
    _patch(videoId=_V2, paused=True)
    assert verify.check(dw) is False


def test_play_and_previous_are_done_when_the_player_runs():
    _playing(paused=True)
    dw_play = _dw("play")
    assert yt.apply_action("play", {}).get("ok")
    assert verify.check(dw_play) is True
    _playing(pos=1, videoId=_V2, paused=True)
    dw_prev = _dw("previous")
    assert yt.apply_action("previous", {}).get("ok")
    assert verify.check(dw_prev) is True


@pytest.mark.parametrize("action", ["play_local", "play_torrent"])
def test_a_stream_is_done_when_its_src_changed_and_it_plays(action):
    _playing()
    dw = _dw(action)
    assert verify.check(dw) is False
    _patch(src="http://127.0.0.1/stream/abc", source="local", videoId="", paused=False)
    assert verify.check(dw) is True
