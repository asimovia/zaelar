"""V2-886 fila 6 — the player state the brain reads is the PLAYER's report when it has one for the loaded video,
never the order; and the loaded video and its state are ONE line. Measured 2026-11-11: «No, está en pausa ahora mismo:
suena X» — the digest said «EN EL REPRODUCTOR: «X»» and, on another line, the state; the state line read `paused` (the
order), so a pause pressed inside the player still read «playing». Disarm: `state_line` back to `paused` → red."""
import pytest

from widgets.youtube import sound

LOADED = {"videoId": "v1", "title": "Like a Prayer", "channel": "Madonna", "volume": 80}


@pytest.mark.parametrize("db,expect", [
    ({**LOADED, "paused": False, "playing_id": "v1", "playing": False}, "en pausa"),        # paused in the iframe
    ({**LOADED, "paused": True, "playing_id": "v1", "playing": True}, "reproduciéndose"),   # played in the iframe
    ({**LOADED, "paused": True}, "en pausa"),                                               # no report yet: the order
    ({**LOADED, "paused": False, "playing_id": "v0", "playing": True}, "reproduciéndose"),  # a report on another video
])
def test_the_state_is_the_players_report(db, expect):
    assert sound.state_line(db).startswith(f"ESTADO DEL REPRODUCTOR: {expect}")


def test_the_loaded_video_and_its_state_are_one_line(monkeypatch):
    from widgets.youtube import data
    db = {**LOADED, "paused": False, "playing_id": "v1", "playing": False}
    monkeypatch.setattr(data, "_load_db", lambda: db, raising=False)
    monkeypatch.setattr(data.store, "load", lambda wid, *a, **k: db, raising=False)
    text = data.prompt_digest() if hasattr(data, "prompt_digest") else ""
    if not text:
        pytest.skip("the digest reader is not reachable without a store")
    lines = [ln for ln in text.splitlines() if "EN EL REPRODUCTOR" in ln or "ESTADO DEL REPRODUCTOR" in ln]
    assert len(lines) == 1 and "en pausa" in lines[0] and "Like a Prayer" in lines[0], lines
