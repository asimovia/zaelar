"""The brain sees what the music card shows, and volume reaches the player making the sound (V2-812 T-02).

Measured on a phone: the card showed a song playing, yet every read of it said «items: NONE — the card is OPEN but
EMPTY» — the only thing the brain got was the saved-lists index, and he had no lists. Asked «are you sure it isn't
muted?», the agent answered it had no data and the card was empty. And the volume, by voice or by the card's own
slider, went to the first connected provider (Spotify, on a device elsewhere) while the sound came from somewhere
else.

Now emptiness is the widget's to say (`refs.items_line` defers to a published interior), the music card publishes
its live state (song, which player and where, playing or paused, volume, a silent browser), and every control goes
to the provider the last start was recorded on (`connectors.music.sounding_provider`).
"""
from __future__ import annotations

import pytest

from connectors import music
from connectors.music import base as mb
from connectors.music import registry
from widgets.musica import data as md


class _Remote(mb.MusicProvider):
    """A connected provider that plays on a device elsewhere, recording what it is asked."""
    name = "spotify"
    plays_elsewhere = True

    def __init__(self):
        self.calls: list = []

    def connected(self): return True
    def search(self, query, limit=5): return []
    def play(self, query="", uri="", device=""): return mb.MusicResult(ok=False, reason="no_track")
    def pause(self): self.calls.append("pause"); return mb.MusicResult(ok=True, provider=self.name)
    def resume(self): return mb.MusicResult(ok=True, provider=self.name)
    def next(self): self.calls.append("next"); return mb.MusicResult(ok=True, provider=self.name)
    def previous(self): return mb.MusicResult(ok=True, provider=self.name)

    def set_volume(self, percent):
        self.calls.append(("volume", percent))
        return mb.MusicResult(ok=True, provider=self.name, action="volume")

    def now_playing(self):
        return mb.NowPlaying(playing=True, volume=40, provider=self.name, device="Home computer",
                             track=mb.Track(id="t9", title="Elsewhere", artist="Someone"))


@pytest.fixture
def card(monkeypatch, tmp_path):
    import widgets.store as store
    from connectors.music import youtube_audio as yta
    from connectors.spotify import auth
    monkeypatch.setattr(store, "_path", lambda wid: str(tmp_path / f"{wid}.json"))
    monkeypatch.setattr(store, "_legacy_path", lambda wid: str(tmp_path / f"{wid}_legacy.json"))
    monkeypatch.setattr(auth, "status", lambda: {"logged_in": True, "can_connect": True})
    remote, page = _Remote(), yta.YouTubeAudioProvider()
    monkeypatch.setattr(registry, "available", lambda: [remote, page])
    monkeypatch.setattr(registry, "get", lambda n: {"spotify": remote, "youtube": page}.get(n))
    store.save("musica", {"yt": {"videoId": "VID00000001", "title": "Dai Dai - Shakira", "paused": False,
                                 "cmd_seq": 2, "volume": 50},
                          "source": {"provider": "youtube", "screen": "mobile:aa11", "query": "shakira"}})
    return remote


def test_a_card_showing_a_song_with_no_lists_is_not_empty(card):
    from nucleo.flash import widget_read
    from widgets import refs
    assert "VACÍA" not in refs.items_line("musica"), "no saved lists is not «nothing on the card»"
    block = widget_read.read("musica")
    assert "Dai Dai" in block and "Shakira" in block, "the song he sees reaches the brain"
    assert "volume 50%" in block and "playing" in block and "phone" in block


def test_a_card_with_nothing_on_it_is_still_said_empty(card):
    import widgets.store as store
    from widgets import refs
    store.save("musica", {})
    md._np_last.update(at=0.0, np=None)
    card.now_playing = lambda: mb.NowPlaying(playing=False, provider="spotify")
    assert "VACÍA" in refs.items_line("musica"), "a truly empty card keeps saying so"


def test_volume_by_voice_and_by_slider_reaches_the_player_that_sounds(card):
    r = music.control("volume_up")
    assert r.ok and md._load_db()["yt"]["volume"] == 65, "50 + a notch, on the page player that sounds"
    md.apply_action("set_volume", {"level": 30})
    assert md._load_db()["yt"]["volume"] == 30
    assert not [c for c in card.calls if isinstance(c, tuple)], "the device elsewhere was never touched"


def test_a_start_recorded_on_the_device_sends_the_controls_there(card):
    music.placement.record("spotify", device_id="pc", device="Home computer", screen="desktop:bb22")
    music.control("set_volume", percent=20)
    music.control("next")
    assert ("volume", 20) in card.calls and "next" in card.calls
    assert "Home computer" in md.prompt_digest(), "the digest names the device it sounds on"

