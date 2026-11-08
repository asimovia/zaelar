"""The file manager's cloud provider is a preference, and each move declares its end state (operator, 2026-11-08).

  · A saved cloud provider (Drive, OneDrive) that is no longer connected — or a connector package that will not load —
    falls back to the local library for that move, with a note in the reply, instead of a dead-stop error.
  · `search_files` / `open_folder` / `set_provider` / `set_view` declare `done_when` on fields of the view;
    `rename_file` / `delete_file` / `save_document` declare row clauses on the `entries` collection the card declares.
  · A rename with no extension keeps the file's own, so the file stays on its shelf (and in the card's sight).
"""
from __future__ import annotations

import importlib
import json
import pathlib

import pytest

_ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture()
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from nucleo import workspace
    from widgets import store as wstore
    importlib.reload(workspace)
    importlib.reload(wstore)
    from widgets.archivos import data as mod
    importlib.reload(mod)
    yield mod
    importlib.reload(workspace)
    importlib.reload(wstore)


class _Svc:
    def __init__(self, connected=True):
        self.connected = connected

    def status(self):
        return {"ok": True, "connected": ["gdrive"] if self.connected else [],
                "providers": [{"id": "gdrive", "label": "Google Drive", "connected": self.connected}]}

    def providers_public(self):
        return [{"id": "gdrive", "label": "Google Drive"}]

    def list_folder(self, provider="", folder_id="", page=""):
        return {"ok": True, "provider": "gdrive", "entries": [{"id": "f1", "name": "Contrato.pdf", "kind": "file"}]}

    def search(self, q, provider=""):
        return self.list_folder()

    def breadcrumb(self, folder_id, provider="", max_depth=12):
        return {"ok": True, "trail": [{"id": folder_id, "name": "Contratos"}] if folder_id else []}


def _manifest() -> dict:
    return json.loads((_ENGINE / "widgets" / "archivos" / "manifest.json").read_text(encoding="utf-8"))


def _dw(action, payload):
    from nucleo.circuit import spec
    return spec.render("archivos", action, payload)


def _saved_cloud_then_disconnected(mod, monkeypatch, svc_after):
    monkeypatch.setattr(mod, "_svc", lambda: _Svc(connected=True))
    assert mod.apply_action("set_provider", {"provider": "gdrive"})["ok"]
    monkeypatch.setattr(mod, "_svc", lambda: svc_after)


# ── the provider is a preference ───────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("lang, word", [("es", "biblioteca"), ("en", "library")])
def test_a_disconnected_cloud_provider_falls_back_to_the_library_with_a_note(data, monkeypatch, lang, word):
    from i18n import langs
    monkeypatch.setattr(langs, "current_code", lambda: lang)
    from library import index
    assert index.save_text("informe anual", "texto")["ok"]
    _saved_cloud_then_disconnected(data, monkeypatch, _Svc(connected=False))
    out = data.apply_action("search_files", {"query": "informe"})
    assert out["ok"] is True, out
    assert out["provider"] == "local" and out["fallback_from"] == "gdrive"
    assert "gdrive" in out["note"] and word in out["note"], out["note"]
    assert [m["name"] for m in out["matches"]] == ["informe anual.md"]
    assert data.view_data()["provider"] == "local", "the view says what it is showing"


def test_a_missing_connector_lands_a_cloud_folder_at_the_library_root(data, monkeypatch):
    _saved_cloud_then_disconnected(data, monkeypatch, None)
    out = data.apply_action("open_folder", {"folderId": "1AbCdriveFolderId"})
    assert out["ok"] is True and out["folder_id"] == "", out
    assert out["fallback_from"] == "gdrive" and out["note"]
    assert any(e["id"] == "shelf:documents" for e in data.view_data()["entries"])


def test_a_connected_cloud_provider_is_still_served_by_the_cloud(data, monkeypatch):
    _saved_cloud_then_disconnected(data, monkeypatch, _Svc(connected=True))
    out = data.apply_action("search_files", {"query": "contrato"})
    assert out["ok"] and "fallback_from" not in out and data.view_data()["provider"] == "gdrive"


# ── the end states ─────────────────────────────────────────────────────────────────────────────────────────
def test_every_declared_end_state_reads_a_field_or_a_declared_collection(data):
    m = _manifest()
    view = data.view_data()
    assert "entries" in (m.get("collections") or {}), "row clauses need a declared collection"
    for action in ("search_files", "open_folder", "set_provider", "set_view",
                   "rename_file", "delete_file", "save_document"):
        dw = m["actions"][action].get("done_when")
        assert dw and dw["widget"] == "archivos", action
        if "field" in dw:
            assert dw["field"] in view, (action, dw["field"])
        else:
            assert dw["collection"] == "entries", action


def test_the_view_moves_are_met_once_the_card_shows_them(data):
    from nucleo.circuit import verify
    for action, payload in (("search_files", {"query": "nada"}), ("open_folder", {"folderId": "video"}),
                            ("set_view", {"mode": "grid"})):
        assert verify.check(_dw(action, payload)) is False, f"{action} before it ran"
        assert data.apply_action(action, payload)["ok"], action
        assert verify.check(_dw(action, payload)) is True, action
    assert data.apply_action("set_provider", {"provider": "local"})["ok"]
    assert verify.check(_dw("set_provider", {"provider": "local"})) is True


def test_saving_renaming_and_deleting_are_read_on_the_rows(data):
    from nucleo.circuit import verify
    saved = _dw("save_document", {"name": "acta", "text": "x"})
    assert verify.check(saved) is False
    out = data.apply_action("save_document", {"name": "acta", "text": "x"})
    assert out["ok"] and verify.check(saved) is True
    rel = out["rel"]
    renamed = _dw("rename_file", {"fileId": rel, "name": "acta final"})
    assert verify.check(renamed) is False
    res = data.apply_action("rename_file", {"fileId": rel, "name": "acta final"})
    assert res["ok"] and verify.check(renamed) is True
    assert res["rel"].endswith("acta final.md"), "a name with no extension keeps the file's own (and its shelf)"
    gone = _dw("delete_file", {"fileId": res.get("rel") or rel})
    assert verify.check(gone) is False, "the file is still on the shelf"
    assert data.apply_action("delete_file", {"fileId": res.get("rel") or rel})["ok"]
    assert verify.check(gone) is True


def test_the_fallback_keeps_his_saved_cloud_choice(data, monkeypatch):
    """A preference is not changed by one unavailable moment: the card shows the library, his choice stays the cloud
    drive, and once it is reachable again the next move goes back to it."""
    _saved_cloud_then_disconnected(data, monkeypatch, _Svc(connected=False))
    data.apply_action("refresh", {})
    from widgets.archivos import data as _d
    assert _d._load().get("preferred_provider") == "gdrive"
    monkeypatch.setattr(_d, "_svc", lambda: _Svc(connected=True))
    out = data.apply_action("refresh", {})
    assert out.get("fallback_from") is None and _d._load().get("provider") == "gdrive", out
