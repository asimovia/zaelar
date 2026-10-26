"""V2-806 F2 — one place per kind of preference: the style knobs, a widget's preferences and the autoresponder's
standing rule are rows of the rules table, each imported once from the store that held it before.

The class: the same kind of thing — «his standing choice about X» — lived in a style file, a consent file, a
widget's own JSON and a global class the autoresponder rewrote for every channel. Each had its own reader and none
could be listed. Generic by construction: a voice knob, a widget's enforceable value and its free-text note, two
messaging platforms.
"""
from __future__ import annotations

import json

import pytest

import rules
from nucleo import consent, style_policy
from widgets import store as wstore


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path / "widgets"))
    monkeypatch.setattr(wstore, "_last_hash", {})
    consent._reset_for_tests()
    yield
    consent._reset_for_tests()


def _user_rows(scope: str) -> list[dict]:
    return [r for r in rules.all_rows(include_defaults=False) if r["scope"] == scope]


# ── the voice knobs ──────────────────────────────────────────────────────────────────────────────────────

def test_a_style_knob_is_a_voice_row_over_its_genesis_default():
    assert style_policy.confirm_short_actions() is True, "genesis"
    assert rules.deciding_rule(rules.path(surface="voice"), "confirm_short_actions")["source"] == "default"
    style_policy.set_pref("confirm_short_actions", False, "no me confirmes las órdenes")
    assert style_policy.confirm_short_actions() is False
    assert [r["key"] for r in _user_rows("voice")] == ["confirm_short_actions"]
    style_policy.retract("confirm_short_actions")
    assert style_policy.confirm_short_actions() is True and _user_rows("voice") == []


def test_the_legacy_style_file_is_imported_once(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "style.json").write_text(json.dumps({"fillers": "off", "max_sentences": 4,
                                                                "_set_at": 1_700_000_000}), encoding="utf-8")
    assert style_policy.filler_mode() == "off" and style_policy.max_sentences() == 4
    first = sorted(r["id"] for r in _user_rows("voice"))
    assert first == ["m_style_fillers", "m_style_max_sentences"]
    from rules import store
    store._conn().execute("DELETE FROM rules_meta")
    store._done.clear()
    style_policy.policy()
    assert sorted(r["id"] for r in _user_rows("voice")) == first, "a re-run inserts nothing"
    rules.remove("m_style_fillers")
    store._done.clear()
    assert style_policy.filler_mode() == "smart", "a row he deleted does not come back from the old file"


# ── a widget's preferences ───────────────────────────────────────────────────────────────────────────────

def test_a_widgets_preferences_are_rows_and_the_card_shows_the_table():
    from widgets.youtube import data as yt
    assert yt.apply_action("set_preference", {"key": "calidad mínima", "value": "1080p"})["ok"]
    assert yt.apply_action("set_preference", {"key": "nada de vídeos de más de una hora"})["ok"]
    rows = {r["key"]: r for r in _user_rows("widget:youtube")}
    assert rows["min_definition"]["value"] == 1080 and rows["note"]["text"] == "nada de vídeos de más de una hora"
    rules.set_value(rows["min_definition"]["id"], 720)               # edited from ⚙ Settings → Rules
    view = yt.view_data()
    assert view["prefs"] == {"min_definition": 720}, "the card reads the table, not a copy of its own"
    assert [n["text"] for n in view["prefs_notes"]] == ["nada de vídeos de más de una hora"]


def test_an_older_store_is_imported_once(tmp_path):
    from widgets.youtube import data as yt
    wstore.save("youtube", {"prefs": {"captions": True}, "prefs_notes": [{"text": "solo documentales",
                                                                          "added_at": 1_700_000_000}]})
    assert yt.view_data()["prefs"] == {"captions": True}
    assert sorted(r["key"] for r in _user_rows("widget:youtube")) == ["captions", "note"]
    yt.view_data()
    assert len(_user_rows("widget:youtube")) == 2, "a second load inserts nothing"
    from rules import store
    store._conn().execute("DELETE FROM rules_meta")
    store._done.clear()
    yt.view_data()
    assert len(_user_rows("widget:youtube")) == 2, "even a re-run of the import inserts nothing: the ids are stable"


# ── the autoresponder's rule is scoped to its platform ───────────────────────────────────────────────────

def test_turning_one_platforms_responder_on_never_opens_another():
    from widgets.mensajeria import autorespond, data
    db = data.load_db()
    autorespond.set_config(db, "whatsapp", text="De viaje hasta el lunes")
    assert consent.class_policy("messaging.autorespond@whatsapp") == "allow"
    assert consent.class_policy("messaging.autorespond@email") == "never"
    assert consent.class_policy("messaging.autorespond") == "never", "the class for every channel is untouched"
    row = rules.deciding_rule(rules.path(cls="messaging.autorespond", channel="whatsapp"))
    assert (row["scope"], row["source"]) == ("messaging/whatsapp/autorespond", "user")
