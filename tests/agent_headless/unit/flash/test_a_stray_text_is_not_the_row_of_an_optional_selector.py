"""A stray text is the row a call names only where the action NEEDS a row; and an open native panel is a fact of the screen (V2-935).

The tester's run (2026-11-18, 13:07): «show me the groups I have on WhatsApp» → the model called the contacts card's
view with `{platform: "whatsapp"}`, a key the action does not declare. The loose-text rule (one text under an
undeclared key IS the row, measured on `set_favorite {contacto: …}`) turned it into `groupId: "whatsapp"`; no such
group, the view was left as it was, and he heard «done». That rule is for an action that cannot run without its row:
where the selector is OPTIONAL a stray text is something else the model meant, and names nothing.

Same run, 12:58: the connectors panel stayed open over everything for three turns while the turn's facts said the
screen was empty. The screen's own report says which native panel is open; the turn's screen line now reads it.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from nucleo.acts import frontend as card_target


@pytest.fixture
def acts(monkeypatch):
    """A card with one action whose row is required and one whose selector is optional."""
    from nucleo.acts import payload_fill
    from widgets import refs
    monkeypatch.setattr(refs, "id_field_for_action", lambda wid, act: "rowId")
    monkeypatch.setattr(refs, "selector_is_optional", lambda wid, act, key="": act == "show_view")
    monkeypatch.setattr(payload_fill, "_payload_spec", lambda wid, act: {"rowId": "", "kind": ""})


def test_where_the_row_is_required_one_stray_text_is_still_the_row(acts):
    assert card_target.payload_ref("people", "set_favorite", {"person": "Quinn Ferrer"}) == "Quinn Ferrer"


@pytest.mark.parametrize("payload", [{"platform": "whatsapp"}, {"source_name": "telegram"}])
def test_where_the_selector_is_optional_a_stray_text_names_nothing(acts, payload):
    assert card_target.payload_ref("people", "show_view", payload) == ""
    assert card_target.payload_ref("people", "show_view", {"rowId": "family", **payload}) == "family", "a declared id still does"


def test_disarm_without_the_optional_check_the_stray_text_becomes_the_row(acts, monkeypatch):
    from widgets import refs
    monkeypatch.setattr(refs, "selector_is_optional", lambda wid, act, key="": False)
    assert card_target.payload_ref("people", "show_view", {"platform": "whatsapp"}) == "whatsapp"


@pytest.mark.parametrize("panel, said", [("conectores", True), ("", False)])
def test_the_turns_screen_line_names_an_open_native_panel(monkeypatch, panel, said):
    from memory import api as memapi
    from nucleo import canvas_focus
    from nucleo.turn.prompt import live_state
    from widgets import screen_doc
    monkeypatch.setattr(memapi, "state", lambda: {"open_widgets": []})
    monkeypatch.setattr(canvas_focus, "phone_front", lambda: None)
    monkeypatch.setattr(screen_doc, "read", lambda dev=None: SimpleNamespace(panel=panel))
    line = live_state.screen_line()
    assert ("«conectores»" in line) is said and "pantalla VACÍA" in line
    monkeypatch.setattr(screen_doc, "read", lambda dev=None: None)      # unknown screen: nothing claimed about a panel
    assert "panel" not in live_state.screen_line()
