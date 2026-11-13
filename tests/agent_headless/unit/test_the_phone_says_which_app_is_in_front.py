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
    memory.set_state({"open_widgets": ["agenda", "musica", "youtube"], "maximized_widget": "", "minimized_widgets": []})
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


# ── 3 · the screen line and the brief's focus name the front app first ────────────────────────────────────────
@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_screen_line_names_the_front_app_first(on, monkeypatch, lang):
    from i18n import langs
    from memory import api as memory
    from nucleo.turn.prompt import live_state
    monkeypatch.setattr(langs, "current_code", lambda: lang)
    memory.set_state({"open_widgets": ["agenda", "musica", "youtube"], "maximized_widget": "musica",
                      "minimized_widgets": ["agenda", "youtube"]})
    on(PHONE)
    line = live_state.screen_line()
    assert "«musica» delante" in line and line.index("musica") < line.index("agenda"), line
    memory.set_state({"maximized_widget": ""})
    assert "INICIO" in live_state.screen_line() and "VACÍA" not in live_state.screen_line()
    on(DESK)
    assert live_state.screen_line() == "En pantalla: agenda, musica, youtube."


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_briefs_focus_on_a_phone_is_the_front_app(on, monkeypatch, lang):
    from i18n import langs
    from memory import api as memory
    from nucleo import canvas_focus
    from nucleo.turn import brief_screen
    monkeypatch.setattr(langs, "current_code", lambda: lang)
    monkeypatch.setattr(canvas_focus, "last_turn_card", lambda ids: "agenda" if "agenda" in ids else "")
    memory.set_state({"maximized_widget": "musica"})
    on(PHONE)
    q = brief_screen.target_question(["agenda", "musica", "youtube"])
    assert q and "PHONE: «musica» is the app in front" in q["instructions"], q and q["instructions"][-300:]
    assert next(iter(q["criteria"])).startswith("musica:"), list(q["criteria"])[:3]
    on(DESK)
    q = brief_screen.target_question(["agenda", "musica", "youtube"])
    assert "previous turn acted on «agenda»" in q["instructions"] and "PHONE" not in q["instructions"]


def test_a_turn_that_moves_to_the_phone_adopts_its_front_app(on):
    """The phone reported while the desktop held the turn (stored, not adopted); his next turn starts on the phone."""
    from memory import api as memory
    from server import canvas_api
    on(DESK)
    asyncio.run(canvas_api.canvas_state({"open": ["agenda", "youtube"], "front": "youtube", "dev": PHONE}))
    canvas_api._adopt(PHONE)
    st = memory.state()
    assert st.get("maximized_widget") == "youtube" and st.get("minimized_widgets") == ["agenda"]
