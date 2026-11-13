"""The music card's page player as the engine hears it: a screen where the card lives, and what that screen REPORTS
through the card's one state door (`widgets/state.py`, V2-884 step 2) — the way a mounted card reports, so a test reads
the same thing the brain and the end states read. Not a test module: the tests of this folder share it."""
from __future__ import annotations

DEV = "mobile:aa11"


def page_player(monkeypatch, dev: str = DEV):
    """Open the music card on `dev` and return `says(**fields)`: one report of its page player, acking the revision
    the card has now (what a card says once it applied what it was told). `full=True` replaces every field."""
    from server import canvas_api
    from voice import screens
    from widgets import state
    for name in ("_SNAP", "_CHANGED", "_COPY", "_EVENTS", "_GONE", "_HELD"):     # given back when the test ends
        monkeypatch.setattr(state, name, {})
    for name in ("_screens", "_playing", "_traces", "_tasks"):
        monkeypatch.setattr(screens, name, type(getattr(screens, name))())
    monkeypatch.setitem(screens._holder, "dev", "")
    monkeypatch.setitem(screens._last, "dev", "")
    screens.attach(dev)
    monkeypatch.setattr(canvas_api, "_BY_DEV", {dev: {"open": ["musica"]}})
    screens.note_playing("musica", dev)
    n = [0]

    def says(full: bool = False, **fields) -> dict:
        n[0] += 1
        code, got = state.report("musica", {"dev": dev, "mount": "m1", "n": n[0], "full": full or n[0] == 1,
                                            "patch": fields, "ack": state.stamp("musica")})
        assert code == 200, got
        return got
    return says
