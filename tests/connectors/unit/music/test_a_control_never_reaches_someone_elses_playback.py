"""A control never reaches a playback that is not ours (operator, 2026-11-08).

Measured on his own engine: one Spotify account shared by a household. A song was sounding on a speaker in another
room; the music card read it as «now playing» and offered ⏸. His tap paused the other person's music, and ▶ would
have restarted it there. The class: a control (pause, resume, skip, volume, seek, queue) on a provider that plays on
its own devices went to whatever device the account was active on, without asking whose playback that was.

Ours = the device the last start placed (`placement.recorded`) or the account's device that sits with the asking
screen (`device_near`). Anything else is refused with `reason="elsewhere"` and the device named; nothing active is
nobody's playback and the control goes ahead. The Spotify Web API is faked; nothing reaches the network.
"""
from __future__ import annotations

import importlib

import pytest

from connectors import music
from connectors.music import placement, registry
from connectors.spotify import client

sp_provider = importlib.import_module("connectors.spotify.provider")

COMPUTER = "desktop:bb22"


def _dev(i, name, kind, active=False):
    return {"id": i, "name": name, "type": kind, "is_active": active, "is_restricted": False}


class _Account:
    def __init__(self, devices, sounding_on=""):
        self.devices = devices
        self.sounding_on = sounding_on
        self.item = "t1"
        self.calls: list = []

    def playback_state(self):
        dev = next((d for d in self.devices if d["id"] == self.sounding_on), None)
        if dev is None:
            return {}
        return {"is_playing": True, "device": {"id": dev["id"], "name": dev["name"], "volume_percent": 40},
                "item": {"id": self.item, "uri": f"spotify:track:{self.item}", "name": "TQG", "artists": [{"name": "KAROL G"}]}}

    def _act(self, name):
        def fn(*a, device_id="", **k):
            self.calls.append(name)
            return {}
        return fn


@pytest.fixture
def account(monkeypatch, tmp_path):
    import widgets.store as store
    from voice import screens
    monkeypatch.setattr(store, "_path", lambda wid: str(tmp_path / f"{wid}.json"))
    monkeypatch.setattr(store, "_legacy_path", lambda wid: str(tmp_path / f"{wid}_legacy.json"))
    monkeypatch.setattr(sp_provider, "_SETTLE_S", 0)
    monkeypatch.setattr(sp_provider.SpotifyProvider, "connected", lambda self: True)
    registry._PROVIDERS.clear()
    registry._loaded = True
    registry.register(sp_provider.SpotifyProvider())
    screens._reset_for_tests()

    def install(acc: _Account):
        monkeypatch.setattr(client, "devices", lambda: list(acc.devices))
        monkeypatch.setattr(client, "playback_state", acc.playback_state)
        for name in ("pause", "resume", "next_track", "previous_track", "set_volume"):
            monkeypatch.setattr(client, name, acc._act(name))
        return acc

    yield install
    screens._reset_for_tests()
    registry._PROVIDERS.clear()
    registry._loaded = False


HOUSE = [_dev("mac", "MacBook Pro", "Computer"), _dev("spk", "Living room", "Speaker", active=True)]


@pytest.mark.parametrize("action", ["pause", "resume", "next", "previous", "volume_up", "set_volume"])
def test_a_speaker_somebody_else_is_using_is_left_alone(account, action):
    acc = account(_Account(HOUSE, sounding_on="spk"))
    placement.record("spotify", device_id="mac", device="MacBook Pro", screen=COMPUTER, query="x")
    r = music.control(action, percent=30)
    assert not r.ok and r.reason == "elsewhere", (r.ok, r.reason)
    assert "Living room" in r.message and r.extra.get("device") == "Living room"
    assert acc.calls == [], f"nothing was sent to the other device: {acc.calls}"


def test_the_device_we_placed_the_music_on_is_ours(account):
    acc = account(_Account(HOUSE, sounding_on="mac"))
    placement.record("spotify", device_id="mac", device="MacBook Pro", screen=COMPUTER, query="x")
    r = music.control("pause")
    assert r.ok and acc.calls == ["pause"]


def test_the_device_beside_the_asking_screen_is_ours(account):
    from voice import screens
    acc = account(_Account([_dev("mac", "MacBook Pro", "Computer", active=True)], sounding_on="mac"))
    screens.begin_turn(COMPUTER, "T1")
    r = music.control("pause")
    assert r.ok and acc.calls == ["pause"]


def test_nothing_sounding_is_nobodys_playback(account):
    acc = account(_Account(HOUSE, sounding_on=""))
    placement.record("spotify", device_id="mac", device="MacBook Pro", screen=COMPUTER, query="x")
    r = music.control("pause")
    assert r.reason != "elsewhere" and acc.calls == ["pause"]


@pytest.mark.parametrize("recorded, want", [("mac", ["mac"]), ("", [])], ids=["ours-listed", "no-record"])
def test_with_nothing_active_a_retry_wakes_only_our_device(account, monkeypatch, recorded, want):
    """No device active: Spotify answers `no_device` and the provider retries on a device of its choosing. That choice
    used to be the FIRST device listed — a speaker in another room, as likely as not."""
    from connectors.spotify.client import SpotifyError
    tried: list = []

    def resume(device_id=""):
        tried.append(device_id)
        if not device_id:
            raise SpotifyError(404, "no_device", "no active device")
        return {}

    devices = [_dev("spk", "Living room", "Speaker"), _dev("mac", "MacBook Pro", "Computer")]
    account(_Account(devices, sounding_on=""))
    monkeypatch.setattr(client, "resume", resume)
    if recorded:
        placement.record("spotify", device_id=recorded, device="MacBook Pro", screen=COMPUTER, query="x")
    music.control("resume")
    assert [d for d in tried if d] == want, tried


# ── A START on an account sounding elsewhere is held and said; taking control is his choice ─────────────────────

def _start_world(account, monkeypatch, sounding_on="spk"):
    from voice import screens
    devices = [_dev("mac", "MacBook Pro", "Computer"), _dev("spk", "Living room", "Speaker", active=True)]
    acc = account(_Account(devices, sounding_on=sounding_on))
    monkeypatch.setattr(client, "search", lambda q, types="track", limit=5: {"tracks": {"items": [
        {"id": "t9", "uri": "spotify:track:t9", "name": "Dai Dai", "artists": [{"name": "Shakira"}]}]}})
    started: list = []

    def play(uris=None, context_uri="", device_id=""):
        started.append(device_id)
        acc.sounding_on = device_id
        acc.item = (uris or ["spotify:track:t1"])[0].rsplit(":", 1)[-1]
        return {}

    monkeypatch.setattr(client, "play", play)
    monkeypatch.setattr(client, "transfer", lambda device_id, play=True: (started.append(("transfer", device_id)),
                                                                        setattr(acc, "sounding_on", device_id))[0] or {})
    screens.begin_turn(COMPUTER, "T1")
    return acc, started


def test_a_start_that_would_cut_another_device_is_held_and_said(account, monkeypatch):
    acc, started = _start_world(account, monkeypatch)
    r = music.control("play", "dai dai de shakira")
    assert not r.ok and r.reason == "elsewhere" and r.extra.get("can_take_over")
    assert "Living room" in r.message
    assert started == [], "nothing was started: the speaker keeps playing"
    assert placement.held().get("query") == "dai dai de shakira"


def test_taking_control_starts_what_was_held_on_our_device(account, monkeypatch):
    acc, started = _start_world(account, monkeypatch)
    music.control("play", "dai dai de shakira")
    r = music.control("take_over")
    assert r.ok, (r.reason, r.message)
    assert started == ["mac"], started
    assert placement.held() == {}, "a held start runs once"


def test_taking_control_with_nothing_held_moves_what_sounds_here(account, monkeypatch):
    acc, started = _start_world(account, monkeypatch)
    r = music.control("take_over")
    assert r.ok and started == [("transfer", "mac")], started
    assert placement.recorded().get("device_id") == "mac"


def test_the_card_is_told_where_the_account_sounds(account, monkeypatch):
    _start_world(account, monkeypatch)
    assert music.elsewhere() == {"provider": "spotify", "device": "Living room"}
    placement.record("spotify", device_id="spk", device="Living room", screen=COMPUTER, query="x")
    assert music.elsewhere() == {}, "where our own start went is ours"
