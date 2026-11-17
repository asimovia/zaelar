"""The face choice is kept per ACCOUNT, sanitised (V2-928).

`/api/settings` key `presence` = {on, face, custom}: the screen paints from localStorage at boot and the server's copy
wins on the reconcile (`frontend/app/presence/state.js`), the same two layers as the theme. The custom face is a small
nested spec drawn on a canvas, so the server keeps only part names, colours, numbers and flags, bounded in size; a
malformed value collapses to {} — the default face (Porcelain), switched on — never to a half-trusted one.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def settings(tmp_path, monkeypatch):
    from config import settings as s
    monkeypatch.setattr(s, "SETTINGS_FILE", tmp_path / "settings.json")
    return s


def test_a_choice_round_trips_through_the_account_copy(settings):
    r = settings.update({"presence": {"on": False, "face": "fenec-3",
                                      "custom": {"head": {"skin": "#ffeedd", "shape": "egg", "w": 1.2}, "eyes": {"lashes": True}}}})
    assert "presence" in r["applied"] and not r["needs_reconnect"]
    got = settings.presence()
    assert got == {"on": False, "face": "fenec-3", "custom": {"head": {"skin": "#ffeedd", "shape": "egg", "w": 1.2}, "eyes": {"lashes": True}}}


def test_anything_but_parts_colours_numbers_and_flags_is_dropped(settings):
    s = settings._sanitize_presence({"on": "yes", "face": "../../etc",
                                     "custom": {"head": {"skin": "url(javascript:x)", "w": float("nan"), "deep": {"a": {"b": 1}}},
                                                "<b>": "#fff", "bg": "#000000"}})
    assert s == {"custom": {"head": {"deep": {}}, "bg": "#000000"}} or s == {"custom": {"head": {}, "bg": "#000000"}}
    assert "on" not in s and "face" not in s


def test_a_malformed_value_is_the_default_never_half_trusted(settings):
    assert settings._sanitize_presence("porcelain") == {}
    assert settings._sanitize_presence(None) == {}
    settings.update({"presence": None})
    assert settings.presence() == {}


def test_disarm_an_unsanitised_store_lets_a_script_through(settings, monkeypatch):
    monkeypatch.setattr(settings, "_sanitize_presence", lambda raw: raw if isinstance(raw, dict) else {})
    settings.update({"presence": {"face": "<img onerror=x>"}})
    assert settings.presence()["face"] == "<img onerror=x>", "the disarm did not land — the guard is elsewhere"
