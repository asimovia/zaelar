"""A canvas gesture is an end state the SCREEN reports; a card's own `close` declares what it really does (V2-873, V7).

Demo pass 2026-11-10, V7: «para el vídeo y cierra youtube» ran the youtube card's own `close` — which EMPTIES the
player — the card stayed open, and nothing could tell: the canvas close owed nothing and the card's `close` declared
no end state («🤷 sin condición declarada»). Now:
  · every close / minimise / full screen the canvas door sends owes `canvas <card> closed|minimized|maximized`, read from
    the canvas report the screen writes (`truth.canvas_state`) — the circuit checks it like any declared end state;
  · youtube's `close` declares its real effect, the player emptied (`videoId` absent), never the card closed;
  · and its descriptor offers no example that calls the card by its own name — the word «close youtube» belongs to the
    canvas close it would otherwise steal (Jev read youtube:close 0.70 over canvas close 0.62).
Disarm: `_owe_the_canvas` owing nothing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from nucleo.circuit import spec, verify
from nucleo.flash import show_target
from voice import trace

_ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture
def screen(monkeypatch):
    shown = {"open_widgets": ["youtube"], "minimized_widgets": [], "maximized_widget": ""}
    from memory import api as memapi
    monkeypatch.setattr(memapi, "state", lambda: dict(shown))
    import server.voice_api as va
    monkeypatch.setattr(va, "open_instances", lambda: list(shown["open_widgets"]))
    monkeypatch.setattr("nucleo.turn.brief.names_elsewhere", lambda *a, **k: False)
    spec.reset()
    yield shown
    spec.reset()


def _owed(tid: str) -> list:
    return [e for e in spec.open_specs() if e.get("trace") == tid and (e.get("done_when") or {}).get("canvas")]


@pytest.mark.parametrize("text", ["cierra youtube", "close youtube"])
def test_a_close_is_owed_to_the_screen(screen, text):
    tid = trace.begin(text)
    with trace.scope(tid):
        assert show_target.close_dispatch({"widget_id": "youtube", "mode": "close"}, lambda *_a, **_k: True,
                                          lambda *a, **k: None, text=text) == "youtube"
    owed = _owed(tid)
    assert owed and owed[0]["done_when"] == {"canvas": "youtube", "expect": "closed"}, owed
    assert verify.check(owed[0]["done_when"]) is False, "the screen still shows the card: unmet"
    screen.update(open_widgets=[])
    assert verify.check(owed[0]["done_when"]) is True


@pytest.mark.parametrize("text", ["apártalo un momento", "put it away for now"])
def test_a_minimise_is_owed_to_the_screen(screen, text):
    tid = trace.begin(text)
    with trace.scope(tid):
        show_target.close_dispatch({"widget_id": "youtube", "mode": "minimize"}, lambda *_a, **_k: True,
                                   lambda *a, **k: None, text=text)
    owed = _owed(tid)
    assert owed and owed[0]["done_when"]["expect"] == "minimized"
    screen.update(minimized_widgets=["youtube"])
    assert verify.check(owed[0]["done_when"]) is True


@pytest.mark.parametrize("text", ["ponlo en pantalla completa", "make it full screen"])
def test_full_screen_is_owed_to_the_screen(screen, text):
    tid = trace.begin(text)
    with trace.scope(tid):
        show_target.fullscreen_dispatch({"widget_id": "youtube", "mode": "on"}, text, lambda *_a, **_k: True,
                                        lambda *a, **k: None, {})
    owed = _owed(tid)
    assert owed and owed[0]["done_when"] == {"canvas": "youtube", "expect": "maximized"}
    assert verify.check(owed[0]["done_when"]) is False
    screen.update(maximized_widget="youtube")
    assert verify.check(owed[0]["done_when"]) is True


def test_youtubes_own_close_declares_the_player_emptied_never_the_card_closed():
    close = json.loads((_ROOT / "widgets/youtube/manifest.json").read_text(encoding="utf-8"))["actions"]["close"]
    assert close["done_when"] == {"widget": "youtube", "field": "videoId", "expect": "absent"}
    from widgets import naming
    names = {n.casefold() for n in naming.catalogue_names("youtube")}
    examples = [x.casefold() for x in re.findall(r"«([^»]+)»", close["desc"])]
    assert examples, "the descriptor gives examples of its own order"
    assert not [x for x in examples if any(n in x for n in names)], (
        f"an example calls the card by its name and steals the canvas close: {examples}")
