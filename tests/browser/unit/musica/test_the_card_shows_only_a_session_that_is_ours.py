"""The music card shows only a session that is ours (operator, 2026-11-08).

«Si está reproduciendo Spotify en otro dispositivo y no es una sesión mía, ¿para qué tenemos que visualizar eso? Nuestro
player de música debería estar en blanco. Y si alguien toma el control de Spotify en otro lado […] se cambia la canción
en el visualizador, los controles se bloquean, se pone que está en otro dispositivo y nos deja un botón de tomar el
control.» Measured before: the card showed a song somebody else played on a speaker, with play/pause/next drawn, and
every tap was refused.

The states, read by `widgets/musica/now_playing._live_fields` from declared facts — where the account sounds
(`music.elsewhere`), whether our last start went to that provider and he has not let it go (`source.live`,
`placement.release`), and a start held for his choice (`placement.held`):

  · sounding on our device                       → our player, controls live
  · elsewhere, never our session                 → blank (idle, or our own page player when it holds a song)
  · elsewhere, our session taken / a held start  → that song, `elsewhere` set (the card locks its controls)
  · elsewhere, after he let it go                → blank
"""
from __future__ import annotations

import pytest

from widgets.musica import data as md
from widgets.musica import now_playing as npm

NP = {"playing": True, "title": "Hips Don't Lie", "artist": "Shakira", "device": "Camaretas", "device_id": "spk",
      "provider": "spotify"}


@pytest.fixture
def world(monkeypatch, tmp_path):
    import widgets.store as store
    monkeypatch.setattr(store, "_path", lambda wid: str(tmp_path / f"{wid}.json"))
    monkeypatch.setattr(store, "_legacy_path", lambda wid: str(tmp_path / f"{wid}_legacy.json"))
    monkeypatch.setattr(npm, "_spotify_status", lambda: {"logged_in": True})
    monkeypatch.setattr(md, "_now_playing", lambda: dict(NP))
    from connectors import music
    away = {"v": {"provider": "spotify", "device": "Camaretas"}}
    monkeypatch.setattr(music, "elsewhere", lambda playing_only=True: dict(away["v"]))
    return away


def _live(source=None, held=None):
    from connectors.music import placement
    if held:
        placement.hold(held)
    db = {"source": source} if source else {}
    return md._live_fields(db)


def test_somebody_elses_session_leaves_our_card_blank(world):
    live = _live()
    assert live["mode"] == "idle" and live["now_playing"] is None and live["elsewhere"] == {}


def test_our_page_player_is_what_the_card_shows_when_spotify_plays_elsewhere(world):
    live = md._live_fields({"source": {"provider": "youtube"}, "yt": {"videoId": "abc", "title": "Born to Run"}})
    assert live["mode"] == "youtube" and live["elsewhere"] == {}


def test_our_session_taken_elsewhere_shows_that_song_locked(world):
    live = _live(source={"provider": "spotify", "device_id": "mac", "live": True})
    assert live["mode"] == "spotify" and live["now_playing"]["title"] == "Hips Don't Lie"
    assert live["elsewhere"] == {"provider": "spotify", "device": "Camaretas"}


def test_a_start_held_for_his_choice_shows_the_way_to_take_control(world):
    live = _live(held={"fn": "play", "query": "born to run"})
    assert live["elsewhere"].get("device") == "Camaretas"


def test_after_he_lets_it_go_the_card_is_blank(world):
    live = _live(source={"provider": "spotify", "device_id": "mac", "live": False})
    assert live["mode"] == "idle" and live["elsewhere"] == {}


def test_sounding_on_our_device_is_our_player(world):
    world["v"] = {}
    live = _live(source={"provider": "spotify", "device_id": "spk", "live": True})
    assert live["mode"] == "spotify" and live["elsewhere"] == {}


def test_letting_it_go_is_a_declared_action_that_ends_our_session(world):
    from connectors.music import placement
    placement.record("spotify", device_id="mac", device="MacBook")
    placement.hold({"fn": "play", "query": "x"})
    assert md.apply_action("release", {})["ok"]
    from widgets import store
    assert (store.load("musica", {}).get("source") or {}).get("live") is False and placement.held() == {}


def test_here_is_what_our_player_sounds_never_another_device(world):
    """The end state of a start is `here.title` changed: a song on another device of the account is not `here`."""
    assert _live(source={"provider": "spotify", "device_id": "mac", "live": True})["here"] == {"title": "", "source": ""}
    yt = md._live_fields({"source": {"provider": "youtube"}, "yt": {"videoId": "abc", "title": "Creep"}})
    assert yt["here"] == {"title": "Creep", "source": "youtube"}
    paused = md._live_fields({"source": {"provider": "youtube"}, "yt": {"videoId": "abc", "title": "Creep", "paused": True}})
    assert paused["here"] == {"title": "", "source": ""}   # a value, never a missing key: a failed start reads unmet
    blocked = md._live_fields({"source": {"provider": "youtube"}, "yt": {"videoId": "abc", "title": "Creep", "audio_blocked": True}})
    assert blocked["here"]["title"] == "", "a page player the browser keeps silent is not sounding"


def test_every_start_declares_that_it_sounds_here():
    import json
    m = json.load(open("widgets/musica/manifest.json", encoding="utf-8"))["actions"]
    for a in ("play", "play_playlist", "play_result", "play_album", "take_over"):
        assert m[a]["done_when"] == {"widget": "musica", "field": "here.title", "expect": "changed"}, a
