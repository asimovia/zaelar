"""A card can upload a file (`ctx.upload` → POST /widgets/{id}/upload) only when its manifest says `"uploads": true`.

The file lands in THAT widget's data dir under a generated name (`up_<random>_<sanitized original>`), so nothing
about the path comes from the browser; the widget then names it in an action. Any other card gets a 403.
"""
from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    from widgets import server_api, store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(server_api.router)
    return TestClient(app), store


def test_the_messaging_card_uploads_into_its_own_dir_under_a_generated_name(client):
    c, store = client
    r = c.post("/widgets/mensajeria/upload", files={"file": ("../../etc/mi foto.jpg", b"\xff\xd8x", "image/jpeg")})
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["name"].startswith("up_") and got["name"].endswith("_mi_foto.jpg") and "/" not in got["name"]
    assert got["type"] == "image" and got["url"] == f"/widgets/mensajeria/asset/{got['name']}"
    assert os.path.isfile(os.path.join(store.data_dir("mensajeria"), got["name"]))


def test_a_card_that_does_not_declare_uploads_gets_none(client):
    c, _ = client
    r = c.post("/widgets/agenda/upload", files={"file": ("x.txt", b"x", "text/plain")})
    assert r.status_code == 403


def test_the_canvas_offers_upload_to_the_card():
    src = open("frontend/app/widgets/desktop.js", encoding="utf-8").read()
    assert "upload:async(file)=>" in src and "/widgets/${baseId}/upload" in src
