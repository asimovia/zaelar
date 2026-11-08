"""Tests for SpotifyProvider (V2-041): mapping to Track/NowPlaying + recovery from NO_ACTIVE_DEVICE. Mocked client."""
import pytest

from connectors.spotify import client as spclient
from connectors.spotify.client import SpotifyError
from connectors.spotify.provider import SpotifyProvider

_TRACK = {"id": "t1", "uri": "spotify:track:t1", "name": "Fly Me to the Moon",
          "artists": [{"name": "Frank Sinatra"}], "album": {"name": "Sinatra", "images": [{"url": "http://art"}]},
          "duration_ms": 148000}


@pytest.fixture
def prov(monkeypatch):
    monkeypatch.setattr(SpotifyProvider, "connected", lambda self: True)
    return SpotifyProvider()


def test_search_maps_tracks(prov, monkeypatch):
    monkeypatch.setattr(spclient, "search", lambda q, types="track", limit=5: {"tracks": {"items": [_TRACK]}})
    hits = prov.search("frank sinatra")
    assert hits and hits[0].title == "Fly Me to the Moon" and hits[0].artist == "Frank Sinatra"
    assert hits[0].label() == "Fly Me to the Moon — Frank Sinatra"


def test_play_query_searches_then_plays(prov, monkeypatch):
    calls = {}
    monkeypatch.setattr(spclient, "search", lambda q, types="track", limit=5: {"tracks": {"items": [_TRACK]}})
    monkeypatch.setattr(spclient, "play", lambda uris=None, context_uri="", device_id="": calls.setdefault("uris", uris))
    r = prov.play(query="frank sinatra")
    assert r.ok and r.track.uri == "spotify:track:t1"
    assert calls["uris"] == ["spotify:track:t1"] and "Fly Me to the Moon" in r.message


def test_play_no_track_found(prov, monkeypatch):
    monkeypatch.setattr(spclient, "search", lambda q, types="track", limit=5: {"tracks": {"items": []}})
    r = prov.play(query="asdkfjhaskdfj")
    assert r.ok is False and r.reason == "no_track"


def test_no_active_device_recovers_with_device_id(prov, monkeypatch):
    monkeypatch.setattr(spclient, "search", lambda q, types="track", limit=5: {"tracks": {"items": [_TRACK]}})
    tried = []

    def _play(uris=None, context_uri="", device_id=""):
        tried.append(device_id)
        if not device_id:
            raise SpotifyError(404, "no_device", "no active device")
        return {}

    monkeypatch.setattr(spclient, "play", _play)
    monkeypatch.setattr(spclient, "devices", lambda: [{"id": "spk1", "is_active": False},
                                                      {"id": "dev9", "is_active": False}])
    # Changed on purpose 2026-11-08 (operator): the retry goes to OUR device — the one the last start placed —
    # never the first listed, which on a shared account is somebody else's speaker.
    from connectors.music import placement
    monkeypatch.setattr(placement, "recorded", lambda: {"provider": "spotify", "device_id": "dev9"})
    r = prov.play(query="frank sinatra")
    assert r.ok and tried == ["", "dev9"]          # 1st without a device (404) → 2nd with our device


def test_no_device_at_all_reports_reason(prov, monkeypatch):
    monkeypatch.setattr(spclient, "search", lambda q, types="track", limit=5: {"tracks": {"items": [_TRACK]}})
    monkeypatch.setattr(spclient, "play",
                        lambda uris=None, context_uri="", device_id="": (_ for _ in ()).throw(
                            SpotifyError(404, "no_device", "x")))
    monkeypatch.setattr(spclient, "devices", lambda: [])
    r = prov.play(query="frank sinatra")
    assert r.ok is False and r.reason == "no_device" and r.message


def test_premium_error_reported(prov, monkeypatch):
    monkeypatch.setattr(spclient, "pause",
                        lambda device_id="": (_ for _ in ()).throw(SpotifyError(403, "premium", "x")))
    r = prov.pause()
    assert r.ok is False and r.reason == "premium"


def test_now_playing_parses_state(prov, monkeypatch):
    monkeypatch.setattr(spclient, "playback_state",
                        lambda: {"is_playing": True, "item": _TRACK, "device": {"name": "iPhone", "volume_percent": 40}})
    np = prov.now_playing()
    assert np.playing and np.track.title == "Fly Me to the Moon" and np.device == "iPhone" and np.volume == 40


# ── V2-717 · the playhead ────────────────────────────────────────────────────────────────────────────────

def test_now_playing_carries_where_the_song_is(prov, monkeypatch):
    """A progress bar for a device that is not here needs the photograph AND the length."""
    monkeypatch.setattr(spclient, "playback_state",
                        lambda: {"is_playing": True, "item": _TRACK, "progress_ms": 61000,
                                 "device": {"name": "Salón", "volume_percent": 40}})
    np = prov.now_playing()
    assert np.progress_ms == 61000 and np.track.duration_ms == 148000


def test_seek_to_a_position_asks_spotify_once_and_says_the_time(prov, monkeypatch):
    seen = {}
    monkeypatch.setattr(spclient, "seek", lambda ms, device_id="": seen.setdefault("ms", ms))
    monkeypatch.setattr(spclient, "playback_state", lambda: pytest.fail("an absolute seek needs no reading"))
    r = prov.seek(125)
    assert r.ok and seen["ms"] == 125000
    assert "2:05" in r.message, r.message


def test_a_relative_seek_reads_the_position_first_because_there_is_no_local_clock(prov, monkeypatch):
    """The device is in another room: «adelanta medio minuto» cannot be answered without asking where we are."""
    seen = {}
    monkeypatch.setattr(spclient, "playback_state",
                        lambda: {"is_playing": True, "item": _TRACK, "progress_ms": 30000, "device": {}})
    monkeypatch.setattr(spclient, "seek", lambda ms, device_id="": seen.setdefault("ms", ms))
    assert prov.seek(30, relative=True).ok
    assert seen["ms"] == 60000


def test_a_relative_seek_with_nothing_playing_refuses_instead_of_seeking_to_zero(prov, monkeypatch):
    monkeypatch.setattr(spclient, "playback_state", lambda: {})
    monkeypatch.setattr(spclient, "seek", lambda ms, device_id="": pytest.fail("nothing to move"))
    r = prov.seek(30, relative=True)
    assert r.ok is False and r.reason == "no_track"


@pytest.mark.parametrize("body, code", [
    ('{"error":{"status":403,"message":"Player command failed: Premium required","reason":"PREMIUM_REQUIRED"}}', "premium"),
    ('{"error":{"status":403,"message":"Player command failed: Restriction violated","reason":"UNKNOWN"}}', "restricted"),
], ids=["premium-required", "restriction-violated"])
def test_a_403_on_the_player_is_premium_only_when_spotify_says_so(body, code):
    """Measured 2026-11-08: pausing with nothing playing answered «needs a Premium account» on a Premium account —
    the 403 was a «Restriction violated», which is not a missing subscription."""
    assert spclient._classify(403, "/me/player/pause", body) == code


class _Single:
    """A single song with nothing around it, as Spotify plays one started by its uri: a «next» ends playback and a
    «previous» is disallowed (403) — both measured live 2026-11-08."""

    def __init__(self):
        self.playing, self.position, self.calls = True, 90_000, []

    def state(self):
        return {"is_playing": self.playing, "progress_ms": self.position,
                "device": {"id": "mac", "name": "MacBook"}, "item": {"id": "t1", "uri": "spotify:track:t1",
                                                                     "name": "Me Enamoré", "artists": []},
                "actions": {"disallows": {"skipping_prev": True}}}

    def next_track(self, device_id=""):
        self.calls.append("next"); self.playing = False; return {}

    def previous_track(self, device_id=""):
        raise SpotifyError(403, "restricted", "Restriction violated")

    def seek(self, ms, device_id=""):
        self.calls.append(("seek", ms)); self.position = ms; return {}

    def resume(self, device_id=""):
        self.calls.append("resume"); self.playing = True; return {}


@pytest.fixture
def single(monkeypatch):
    import importlib
    spp = importlib.import_module("connectors.spotify.provider")
    s = _Single()
    monkeypatch.setattr(spp, "_SETTLE_S", 0)
    monkeypatch.setattr(spclient, "playback_state", s.state)
    for n in ("next_track", "previous_track", "seek", "resume"):
        monkeypatch.setattr(spclient, n, getattr(s, n))
    return s


def test_a_next_with_nothing_after_never_leaves_the_music_off(prov, single):
    r = prov.next()
    assert not r.ok and r.reason == "no_next"
    assert single.playing and single.calls[-1] == "resume", single.calls


def test_a_previous_with_nothing_before_starts_the_song_over(prov, single):
    r = prov.previous()
    assert r.ok and ("seek", 0) in single.calls and single.playing
