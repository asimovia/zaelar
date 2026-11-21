"""A close of everything counts the native surface over the canvas, never only the cards (INI-042 #47).

Measured on a cloud session: «abre los ajustes de voz» opened Settings (`voice_settings`), then «cierra todo» sent the
bare close-all, Settings stayed open over an empty canvas and the agent said «Ya no queda nada en pantalla.» The
receipt was built from the open CARDS alone, and the client's `closeAll` closed cards alone.

The class: what a close-all reports as closed or still on screen is read from the screen's own document, panel
included (`screen_doc.panel_over`) — the conversation itself is never «on screen». The client half (the desk's and the
deck's `closeAll` shut their native surfaces) is rendered in `tests/browser/unit/screen/test_close_all_closes_the_panels.py`.
"""
from __future__ import annotations

import pytest

from nucleo import done_ops
from nucleo.flash import card_receipt
from nucleo.acts import bulk_close
from widgets import screen_doc


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    done_ops.reset()
    bulk_close.reset()
    from nucleo.acts import canvas_turn
    monkeypatch.setattr(canvas_turn, "request_of", lambda brief=None, text=None, **k: {
        "text": text or "", "turn_credit": True, "last_reply": "", "verdict": {"canvas": ("close", 0.9)}})
    yield
    done_ops.reset()
    bulk_close.reset()


@pytest.fixture
def es(monkeypatch):
    from i18n import langs
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec("es"))
    return langs.spec("es")


def _doc(monkeypatch, panel):
    monkeypatch.setattr(screen_doc, "read", lambda dev=None: type("D", (), {"panel": panel})())


@pytest.mark.parametrize("panel,want", [("config", "config"), ("chat", ""), ("chat:procesos", "procesos"),
                                        ("settings", "settings"), ("", "")])
def test_the_panel_over_names_every_surface_but_the_conversation(monkeypatch, panel, want):
    _doc(monkeypatch, panel)
    assert screen_doc.panel_over() == want


def test_an_unknown_screen_has_no_panel(monkeypatch):
    monkeypatch.setattr(screen_doc, "read", lambda dev=None: None)
    assert screen_doc.panel_over() == ""


def test_close_all_over_settings_says_it_closed_settings(monkeypatch, es):
    _doc(monkeypatch, "config")
    bulk_close.close_all(lambda *a, **k: None, src="flash", text="cierra todo", open_ids=[])
    line = bulk_close.take_receipt()
    assert line.startswith("He cerrado") and "Ajustes" in line and line.endswith(es.receipt_left_none), line


def test_a_spared_card_leaves_settings_on_screen_and_the_receipt_says_so(monkeypatch, es):
    _doc(monkeypatch, "config")
    done_ops.note("documento", "show", {})
    bulk_close.close_all(lambda *a, **k: None, src="flash", text="cierra lo que no uses", open_ids=["documento", "navegador"])
    line = bulk_close.take_receipt()
    assert "Ajustes" in line.split("He cerrado", 1)[1].split(".", 1)[1], line   # in «still on screen», not «closed»


def test_a_card_closed_under_settings_never_says_nothing_is_left(monkeypatch, es):
    _doc(monkeypatch, "config")
    lines = card_receipt.lines_for("Vale.", [("musica", card_receipt.CLOSE, "")], open_ids=["musica"], lang=es)
    assert lines and "Ajustes" in lines[-1] and es.receipt_left_none not in lines, lines


def test_disarmed_the_receipt_lies_again(monkeypatch, es):
    """RED proof: with the panel unread (the old enumeration — cards only) the session's line comes back."""
    _doc(monkeypatch, "config")
    real = bulk_close._panel_over
    bulk_close._panel_over = lambda: ""
    try:
        bulk_close.close_all(lambda *a, **k: None, src="flash", text="cierra todo", open_ids=[])
        assert bulk_close.take_receipt() == es.receipt_left_none, "the disarm did not land"
    finally:
        bulk_close._panel_over = real
    bulk_close.close_all(lambda *a, **k: None, src="flash", text="cierra todo", open_ids=[])
    assert "Ajustes" in bulk_close.take_receipt()
