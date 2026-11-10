"""`GET /api/daemon/status` says, per platform, whether the PUBLISHED release is signed by the publisher's operating-
system identity (V2-869 §5) — read from that release's `update-manifest.json`, which measures it from the bytes.

  · `downloads.platforms.<os>.signed` is `true`/`false` from the manifest, `null` while it is not known (never read,
    offline, an older manifest without the field) — the screen then shows the unsigned sentence, the safe one;
  · the notarized `.pkg` link appears only when the manifest LISTS it under `installers` (a release signed without
    the Installer identity has no package, and a link to it would 404);
  · the read happens in the background and never blocks the status the icon polls; inside the suite it never runs
    (root conftest), and nothing is read from a non-https base.

Disarm (seen red 2026-11-10): `entry["signed"] = signed.get(name)` replaced by `True` → the unknown test fails.
"""
from __future__ import annotations

import io
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server import daemon_api, daemon_downloads

BASE = daemon_downloads._RELEASE_BASE_DEFAULT


def _cache(monkeypatch, signed: dict) -> None:
    import time
    monkeypatch.setattr(daemon_downloads, "_signed_cache",
                        {"at": time.time(), "base": BASE, "signed": signed, "busy": False})


def test_unknown_is_null_and_nothing_is_fetched_inside_the_suite(monkeypatch):
    started = []
    monkeypatch.setattr(daemon_downloads.threading, "Thread", lambda *a, **k: started.append(k) or None)
    platforms = daemon_downloads._downloads("0.2.2")["platforms"]
    assert platforms["macos"]["signed"] is None and platforms["windows"]["signed"] is None
    assert "package" not in platforms["macos"]
    assert started == [], "LIVE is off in the suite: no background read"


def test_the_flags_and_the_package_come_from_the_manifest(monkeypatch):
    _cache(monkeypatch, {"macos": True, "windows": False, "package:macos": "Zaelar-macos.pkg"})
    platforms = daemon_downloads._downloads("0.2.2")["platforms"]
    assert platforms["macos"]["signed"] is True and platforms["windows"]["signed"] is False
    assert platforms["macos"]["package"] == f"{BASE}/Zaelar-macos.pkg"
    assert "package" not in platforms["windows"]


def test_a_signed_release_without_an_installer_package_links_no_package(monkeypatch):
    _cache(monkeypatch, {"macos": True})
    assert "package" not in daemon_downloads._downloads("0.2.2")["platforms"]["macos"]


def test_the_status_route_carries_the_flag(tmp_path, monkeypatch):
    _cache(monkeypatch, {"macos": True, "windows": True})
    monkeypatch.setattr(daemon_api, "_state_dir", lambda: tmp_path / "config" / "daemon")
    monkeypatch.setattr(daemon_api, "_is_cloud", lambda: False)
    app = FastAPI()
    app.include_router(daemon_api.router)
    body = TestClient(app).get("/api/daemon/status").json()
    assert body["downloads"]["platforms"]["macos"]["signed"] is True


def test_the_reader_takes_only_booleans_and_listed_packages(monkeypatch):
    manifest = {"platforms": {"macos": {"signed": True}, "macos-x86_64": {"signed": "yes"},
                              "windows": {"signed": False}, "pyz": {}},
                "installers": {"macos": {"asset": "Zaelar-macos.pkg"}}}
    seen = []

    def fake_open(url, timeout):
        seen.append(url)
        return io.BytesIO(json.dumps(manifest).encode())

    monkeypatch.setattr(daemon_downloads.urllib.request, "urlopen", fake_open)
    got = daemon_downloads._read_signed(BASE)
    assert seen == [f"{BASE}/update-manifest.json"]
    assert got == {"macos": True, "windows": False, "package:macos": "Zaelar-macos.pkg"}


def test_a_failed_read_is_retried_sooner_than_a_good_one(monkeypatch):
    monkeypatch.setattr(daemon_downloads, "_read_signed", lambda base: (_ for _ in ()).throw(OSError("offline")))
    daemon_downloads._refresh_signed(BASE)
    c = daemon_downloads._signed_cache
    assert c["signed"] == {} and c["busy"] is False and c["base"] == BASE
    import time
    age = time.time() - c["at"]
    assert daemon_downloads._SIGNED_TTL_S - daemon_downloads._SIGNED_RETRY_S - 5 < age < daemon_downloads._SIGNED_TTL_S
