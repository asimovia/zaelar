"""Music plays where he listens, and «playing» is read back, not assumed (V2-812 T-01).

Measured on a phone in a moving car: a Spotify account was connected, so every «play» went to Spotify, which played
on its active device or the first one it listed — not the phone. The API answered 204, the card showed the cover,
the agent said «it's playing» and sent play four more times; the phone produced nothing. The class: a provider that
plays on a device ELSEWHERE was chosen without asking where the request came from, and its 204 was taken for sound.

Now the start is placed on the screen that asked (`voice.screens`): a device of that provider that sits with that
kind of screen, else the page player of that screen; a start on a device elsewhere is read back from the player and
falls back to the page when the device stays silent; the same words again while it sounds are not re-sent; and the
record of where it went is what the controls reach. The Spotify Web API and the YouTube resolver are faked; nothing
reaches the network or a real device.
"""
from __future__ import annotations

import importlib

import pytest

from connectors import music
from connectors.music import registry
from connectors.music import youtube_audio as yta
from connectors.spotify import client

sp_provider = importlib.import_module("connectors.spotify.provider")

PHONE, COMPUTER = "mobile:aa11", "desktop:bb22"


class _Spotify:
    """A fake Spotify account: devices, and a player that sounds only on devices allowed to."""

    def __init__(self, devices, sounds_on=None):
        self.devices = devices
        self.sounds_on = set(sounds_on if sounds_on is not None else [d["id"] for d in devices])
        self.plays, self.paused, self.volumes = [], 0, []
        self.state = {}

    def list_devices(self):
        return list(self.devices)

    def play(self, uris=None, context_uri="", device_id=""):
        dev = next((d for d in self.devices if d["id"] == device_id), None)
        if dev is None:
            dev = next((d for d in self.devices if d.get("is_active")), None) or self.devices[0]
        self.plays.append({"uris": uris, "device_id": device_id, "on": dev["id"]})
        uri = (uris or ["spotify:track:x"])[0]
        self.state = {"is_playing": dev["id"] in self.sounds_on,
                      "device": {"id": dev["id"], "name": dev["name"], "volume_percent": 40},
                      "item": {"id": uri.rsplit(":", 1)[-1], "uri": uri, "name": "Dai Dai",
                               "artists": [{"name": "Shakira"}]}}
        return {}

    def playback_state(self):
        return dict(self.state)

    def pause(self, device_id=""):
        self.paused += 1
        if self.state:
            self.state["is_playing"] = False
        return {}

    def set_volume(self, pct, device_id=""):
        self.volumes.append(pct)
        return {}


def _dev(i, name, kind, active=False):
    return {"id": i, "name": name, "type": kind, "is_active": active, "is_restricted": False}


@pytest.fixture
def world(monkeypatch, tmp_path):
    import widgets.store as store
    from voice import screens
    monkeypatch.setattr(store, "_path", lambda wid: str(tmp_path / f"{wid}.json"))
    monkeypatch.setattr(store, "_legacy_path", lambda wid: str(tmp_path / f"{wid}_legacy.json"))
    monkeypatch.setattr(sp_provider, "_SETTLE_S", 0)
    monkeypatch.setattr(sp_provider.SpotifyProvider, "connected", lambda self: True)
    monkeypatch.setattr(yta, "_resolve", lambda q: ("vidDaiDai01", f"{q} (Official Audio)"))
    monkeypatch.setattr(client, "search", lambda q, types="track", limit=5: {"tracks": {"items": [
        {"id": "t1", "uri": "spotify:track:t1", "name": "Dai Dai", "artists": [{"name": "Shakira"}]}]}})
    registry._PROVIDERS.clear()
    registry._loaded = True
    registry.register(sp_provider.SpotifyProvider())
    registry.register(yta.YouTubeAudioProvider())
    screens._reset_for_tests()

    def install(fake: _Spotify):
        monkeypatch.setattr(client, "devices", fake.list_devices)
        for name in ("play", "playback_state", "pause", "set_volume"):
            monkeypatch.setattr(client, name, getattr(fake, name))
        return fake

    yield install
    screens._reset_for_tests()
    registry._PROVIDERS.clear()
    registry._loaded = False


def _ask_from(dev):
    from voice import screens
    screens.begin_turn(dev, "T1")


def test_a_phone_with_no_spotify_device_plays_in_its_own_page(world):
    fake = world(_Spotify([_dev("pc", "Home computer", "Computer", active=True)]))
    _ask_from(PHONE)
    r = music.control("play", "Shakira")
    assert r.ok and r.provider == "youtube", "nothing of Spotify sits with the phone: the phone's page plays it"
    assert fake.plays == [], "the song was never sent to the computer at home"
    rec = music.placement.recorded()
    assert rec["provider"] == "youtube" and rec["screen"] == PHONE


def test_a_device_on_the_asking_screen_is_the_one_played_and_named(world):
    fake = world(_Spotify([_dev("pc", "Home computer", "Computer", active=True),
                           _dev("ph", "Ricart's phone", "Smartphone")]))
    _ask_from(PHONE)
    r = music.control("play", "Shakira")
    assert r.ok and r.provider == "spotify"
    assert fake.plays[-1]["device_id"] == "ph", "the phone's own Spotify, not the active computer"
    assert "Ricart's phone" in r.message, "the reply names where it sounds, read back from the player"
    assert music.placement.recorded()["device"] == "Ricart's phone"


def test_a_start_the_device_never_sounds_falls_back_to_the_page(world):
    fake = world(_Spotify([_dev("ph", "Ricart's phone", "Smartphone")], sounds_on=[]))
    _ask_from(PHONE)
    r = music.control("play", "Shakira")
    assert fake.plays, "the device on his screen was tried first"
    assert r.ok and r.provider == "youtube", "a 204 with no sound is not «playing»: the page plays it instead"
    assert fake.paused >= 1, "the silent device is stopped so it cannot start late under the page player"


def test_a_chosen_device_that_is_gone_is_never_swapped_for_another(world, monkeypatch):
    fake = world(_Spotify([_dev("pc", "Home computer", "Computer"), _dev("ph", "Ricart's phone", "Smartphone")]))
    from connectors.spotify.client import SpotifyError

    def gone(uris=None, context_uri="", device_id=""):
        fake.plays.append({"device_id": device_id})
        if device_id != "pc":
            raise SpotifyError(404, "no_device", "Device not found")
        return {}
    monkeypatch.setattr(client, "play", gone)
    _ask_from(PHONE)
    r = music.control("play", "Shakira")
    assert [p["device_id"] for p in fake.plays] == ["ph"], "the first listed device is not a fallback for his phone"
    assert r.ok and r.provider == "youtube", "the phone's page plays it instead"


def test_the_same_words_again_while_it_sounds_are_not_sent_again(world):
    fake = world(_Spotify([_dev("ph", "Ricart's phone", "Smartphone")]))
    _ask_from(PHONE)
    assert music.control("play", "Shakira").ok
    again = music.control("play", "shakira")
    assert len(fake.plays) == 1, "a repeated play restarted the song on the device"
    assert again.ok and again.extra.get("noop") and "Ricart's phone" in again.message


def test_without_a_known_screen_the_old_choice_stands_but_is_read_back(world):
    fake = world(_Spotify([_dev("pc", "Home computer", "Computer", active=True)]))
    r = music.control("play", "Shakira")
    assert r.provider == "spotify" and fake.plays, "no screen to place it on: the provider's own device"
    assert r.ok and "Home computer" in r.message, "and the reply says WHERE it went"
    fake.sounds_on.clear()
    r2 = music.control("play", "something else")
    assert not r2.ok and r2.reason == "not_sounding", "silence on the device is said, never «it's playing»"
