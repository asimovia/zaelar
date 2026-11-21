"""The phone says which app is IN FRONT, and the brain reads it (V2-903, phone UI §5a).

A phone shows one app at a time: the deck pages between them and the rest wait hidden behind. It reported only the
whole deck (`{open, dev, by}`), never which one was in front, and said nothing when he paged. So on a phone turn the
brain answered «it», «this one» or «pause» from guesses: the app the previous turn touched, or the DESKTOP's last
geometry (`canvas_layout`, one per install), and its screen line listed every app as «on screen».

Now the deck reports `front` («» on its home) on every report and on every page change. The server stores it as
`maximized_widget` and the rest as `minimized_widgets`, the facts their readers already use. `«that»` never falls back
to the desktop's geometry on a phone turn. The screen line and the brief's focus name the front app first. A desktop
turn reads exactly what it read before. Each case runs the two screens: a desktop and a phone.

Disarms: drop the server's `front` branch, the executor's phone guard, or the brief's front focus → red.
"""
from __future__ import annotations

import asyncio
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
PHONE, DESK = "mobile:p-ava", "desktop:d-ava"


@pytest.fixture
def on(monkeypatch):
    """Run the turn on a given screen (`voice.screens.current`)."""
    from voice import screens

    def _on(dev: str):
        monkeypatch.setattr(screens, "current", lambda: dev)
    return _on


def _report(payload: dict) -> dict:
    from memory import api as memory
    from server import canvas_api
    asyncio.run(canvas_api.canvas_state(payload))
    return memory.state()


# ── 1 · the deck reports its front app, and reports again when he pages ─────────────────────────────────────────
def test_the_deck_reports_the_front_app_and_every_page_change():
    deck = (ROOT / "frontend/mobile/app/shell/Deck.js").read_text()
    report = deck[deck.index("  _reportOpen() {"):deck.index("  // ── paging")]
    assert "front, dev" in report and "this.order[this.at]" in report, "the deck's report does not say which app is in front"
    goto = deck[deck.index("  _goTo(i, dir) {"):deck.index("  _paint() {")]
    assert "this._reportOpen()" in goto, "paging changes the front app and the deck says nothing"


@pytest.mark.parametrize("front,want_max,want_min", [
    ("musica", "musica", ["agenda", "youtube"]),          # an app in front, two behind
    ("", "", ["agenda", "musica", "youtube"]),            # his phone's home: nothing in front
])
def test_the_server_stores_the_phones_front_app(on, front, want_max, want_min):
    on(PHONE)
    st = _report({"open": ["agenda", "musica", "youtube"], "front": front, "dev": PHONE})
    assert st.get("maximized_widget") == want_max
    assert sorted(st.get("minimized_widgets") or []) == want_min


def test_a_desktop_report_is_read_as_before(on):
    on(DESK)
    st = _report({"open": ["agenda", "musica"], "dev": DESK,
                  "layout": [{"id": "agenda", "max": "1"}, {"id": "musica", "min": "1"}]})
    assert st.get("maximized_widget") == "agenda" and st.get("minimized_widgets") == ["musica"]


# ── 2 · «that» on a phone never comes from the desktop's geometry ──────────────────────────────────────────────
@pytest.fixture
def desk_geometry(monkeypatch):
    """The install's last DESKTOP layout says youtube is on top; three apps are open; nothing is maximized."""
    from memory import api as memory
    from server import voice_api
    monkeypatch.setattr(voice_api, "open_instances", lambda: ["agenda", "musica", "youtube"])
    memory.set_state({"open_widgets": ["agenda", "musica", "youtube"], "maximized_widget": "", "minimized_widgets": [],
                      "front_reported": True})
    memory.kv_set("canvas_layout", {"items": [{"id": "agenda", "t": "1", "z": "1"}, {"id": "musica", "t": "2", "z": "2"},
                                              {"id": "youtube", "t": "9", "z": "9"}]})


def test_that_on_a_phone_is_not_the_desktops_top_card(on, desk_geometry):
    from nucleo.actionmap import executor
    on(DESK)
    assert executor._card_in_front() == "youtube", "the desktop reading changed"
    on(PHONE)
    assert executor._card_in_front() == "", "a phone turn read the desktop's geometry"


def test_that_on_a_phone_is_its_front_app(on, desk_geometry):
    from memory import api as memory
    from nucleo.actionmap import executor
    memory.set_state({"maximized_widget": "musica"})
    on(PHONE)
    assert executor._card_in_front() == "musica"


def test_a_turn_that_moves_to_the_phone_adopts_its_front_app(on):
    """The phone reported while the desktop held the turn (stored, not adopted); his next turn starts on the phone."""
    from memory import api as memory
    from server import canvas_api
    on(DESK)
    asyncio.run(canvas_api.canvas_state({"open": ["agenda", "youtube"], "front": "youtube", "dev": PHONE}))
    canvas_api._adopt(PHONE)
    st = memory.state()
    assert st.get("maximized_widget") == "youtube" and st.get("minimized_widgets") == ["agenda"]


# ── audit of e1ca0d99b: what the front app must NOT leak into, and the clients that send none ─────────────────────
def test_the_front_app_never_rides_the_cached_memory_block_nor_the_dossier():
    """P2-1: every turn on a phone changes `maximized_widget`; a cached block that printed it was a turn behind."""
    from memory._prompt import compose
    from nucleo.memory_agent import dossier
    st = {"maximized_widget": "musica", "front_reported": True, "favourite_bike": "a gravel bike"}
    sit, _crit = compose._situation(st, "Ava")
    lines = sit + dossier._state_lines(st)
    assert not any("Maximized" in ln or "Front reported" in ln for ln in lines), lines
    assert any("gravel bike" in ln for ln in sit), "the custom scalars of his state are still rendered"


@pytest.mark.parametrize("dev,label,absent", [
    (PHONE, "DELANTE (teléfono)", "A PANTALLA COMPLETA"),
    (DESK, "A PANTALLA COMPLETA", "DELANTE"),
])
def test_the_front_app_is_in_front_on_a_phone_and_full_screen_on_a_desktop(on, dev, label, absent):
    """P2-2: on a phone the front app was labelled «A PANTALLA COMPLETA (para salir: fullscreen_widget)» — an exit
    the deck does not have, so «hazlo más pequeño» ended in «Hecho» over nothing."""
    from memory import api as memory
    from widgets import brief
    memory.set_state({"open_widgets": ["agenda", "musica"], "maximized_widget": "musica",
                      "minimized_widgets": ["agenda"], "front_reported": dev == PHONE})
    on(dev)
    out = brief.for_prompt(open_ids=["agenda", "musica"])
    assert label in out and absent not in out, out[-600:]


def test_a_phone_report_during_a_desktop_turn_never_touches_the_state(on):
    """P3: the phone reports while the desktop holds the turn — stored for the phone, the brain's screen untouched."""
    from memory import api as memory
    on(DESK)
    _report({"open": ["agenda"], "dev": DESK, "layout": [{"id": "agenda", "max": "1"}]})
    st = _report({"open": ["musica", "youtube"], "front": "youtube", "dev": PHONE})
    assert st.get("open_widgets") == ["agenda"] and st.get("maximized_widget") == "agenda"
    assert not st.get("front_reported")
    assert memory.state().get("minimized_widgets") == []
