"""The photo gallery declares the end state of each move and never dead-stops on its provider (operator, 2026-11-08).

  · `search` / `pick` / `more` / `clear_search` declare `done_when` on fields the view carries as VALUES — a key the view
    omits reads «unverifiable», never unmet, so the search's query travels as `query` ("" with no search on screen).
  · Google Photos is a PREFERENCE: with the connector package missing, `search` still answers from what was imported;
    `pick` with nothing connected OFFERS what works without Google (local images, the files card) beside the connect
    path, in the agent's language, instead of a bare `needs_connect` stop.
"""
from __future__ import annotations

import importlib
import json
import pathlib

import pytest

_ENGINE = pathlib.Path(__file__).resolve().parents[4]
_ITEMS = [{"id": "p1", "filename": "marruecos_01.jpg", "taken_at": "2025-04-02", "provider": "google-photos"},
          {"id": "p2", "filename": "playa.jpg", "taken_at": "2024-08-10", "provider": "google-photos"}]


@pytest.fixture()
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from nucleo import workspace
    from widgets import store as wstore
    importlib.reload(workspace)
    importlib.reload(wstore)
    from widgets.fotos import data as mod
    importlib.reload(mod)
    yield mod
    importlib.reload(workspace)
    importlib.reload(wstore)


class _Svc:
    def __init__(self, connected=True, items=None, pick=None, has_more=False):
        self.connected, self.items, self.has_more = connected, list(items or []), has_more
        self.pick = pick or {"ok": True, "picker_uri": "https://photos.google.com/picker/s1"}
        self.pending = False

    def status(self):
        return {"ok": True, "app_configured": True, "connected": self.connected, "session_pending": self.pending}

    def start_session(self):
        if self.pick.get("ok"):
            self.pending = True
        return dict(self.pick)

    def poll_session(self):
        return {"ok": True, "pending": self.pending, "ready": False}

    def list_page(self, offset=0, size=120):
        sl = self.items[offset:offset + 1]
        return {"items": sl, "next_offset": offset + len(sl), "has_more": offset + len(sl) < len(self.items),
                "total": len(self.items)}

    def years(self):
        return []

    def search(self, q):
        hits = [it for it in self.items if q.lower() in it["filename"]]
        return {"ok": True, "count": len(hits), "date_from": "", "date_to": "", "label": q, "items": hits}


def _actions() -> dict:
    return json.loads((_ENGINE / "widgets" / "fotos" / "manifest.json").read_text(encoding="utf-8"))["actions"]


def _dw(action, payload):
    from nucleo.circuit import spec
    return spec.render("fotos", action, payload)


def test_every_declared_end_state_reads_a_key_the_view_writes_as_a_value(data):
    view = data.view_data()
    for action in ("search", "pick", "more", "clear_search"):
        dw = _actions()[action].get("done_when")
        assert dw and dw.get("widget") == "fotos", action
        assert dw["field"].split(".", 1)[0] in view, f"{action}: «{dw['field']}» is not in the view"
    assert view["query"] == "", "no search on screen is a VALUE, never a missing key"


def test_a_search_is_met_only_once_its_query_is_on_screen(data, monkeypatch):
    from nucleo.circuit import verify
    monkeypatch.setattr(data, "_svc", lambda: _Svc(items=_ITEMS))
    assert verify.check(_dw("search", {"query": "marruecos"})) is False, "nothing searched yet: unmet, not unreadable"
    assert data.apply_action("search", {"query": "marruecos"})["ok"]
    assert verify.check(_dw("search", {"query": "marruecos"})) is True
    assert verify.check(_dw("clear_search", {})) is False, "a filter is on"
    assert data.apply_action("clear_search", {})["ok"]
    assert verify.check(_dw("clear_search", {})) is True


def test_a_picker_that_opened_and_a_page_that_loaded_are_met(data, monkeypatch):
    from nucleo.circuit import verify
    svc = _Svc(items=_ITEMS)
    monkeypatch.setattr(data, "_svc", lambda: svc)
    data.apply_action("refresh", {})
    more = _dw("more", {})
    pick = _dw("pick", {})
    assert verify.check(pick) is False
    assert data.apply_action("pick", {})["ok"] and verify.check(pick) is True
    assert data.apply_action("more", {})["ok"] and verify.check(more) is True


def test_a_search_answers_from_what_was_imported_with_no_connector(data, monkeypatch):
    from connectors.photos import store as pstore
    monkeypatch.setattr(data, "_svc", lambda: None)
    monkeypatch.setattr(pstore, "filter_items", lambda a, b, q, d=None: [it for it in _ITEMS if q in it["filename"]])
    out = data.apply_action("search", {"query": "marruecos"})
    assert out["ok"] is True and out["source"] == "local", out
    assert [m["id"] for m in out["matches"]] == ["p1"]
    assert data.view_data()["query"] == "marruecos"
    assert data.apply_action("pick", {})["ok"] is False, "the picker itself still needs the connector"


@pytest.mark.parametrize("lang, words", [("es", ["Conectores", "imágenes", "Archivos"]),
                                         ("en", ["Connectors", "images", "Files"])])
def test_a_pick_with_nothing_connected_offers_the_alternatives(data, monkeypatch, lang, words):
    from i18n import langs
    monkeypatch.setattr(langs, "current_code", lambda: lang)
    monkeypatch.setattr(data, "_svc", lambda: _Svc(connected=False, pick={
        "ok": False, "error": "Google Photos no está conectado todavía", "needs_connect": True}))
    out = data.apply_action("pick", {})
    assert out["ok"] is False and out["needs_connect"] is True, "the connect path stays"
    targets = {(a.get("widget") or a.get("tool"), a.get("action")) for a in out["alternatives"]}
    assert {("imagenes", "local"), ("archivos", "open_folder"), ("show_panel", None)} <= targets
    for w in words:
        assert w in out["message"], (w, out["message"])
