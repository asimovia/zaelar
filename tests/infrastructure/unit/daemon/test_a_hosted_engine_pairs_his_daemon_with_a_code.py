"""A hosted engine pairs his daemon with a one-time code, and its status says what the relay sees (V2-575 P3).

A hosted engine cannot read the daemon's token off his disk, so `POST /api/daemon/pair` asks the service it reports to
for a code (`POST /daemon/pairing-code`, the engine's own credential) and returns `{code, expires_at}` for him to type
into his daemon. A cloud engine with no relay to ask answers `relay_not_available`; over loopback nothing needs pairing
(unchanged). `/api/daemon/status` carries `relay: {paired, connected, caps, version, platform, since}` — all-false when
there is no relay. A cross-site page is refused on the hosted door too.

The service is faked at the engine's one seam (`relay_link._http`).
Disarm: the hosted branch removed (cloud → `relay_not_available` always) → red.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from starlette.requests import Request


def _req(*, origin: str = "", host: str = "agent.example") -> Request:
    headers = [(b"host", host.encode())]
    if origin:
        headers.append((b"origin", origin.encode()))
    return Request({"type": "http", "method": "POST", "path": "/api/daemon/pair", "headers": headers,
                    "client": ("10.0.0.7", 50000), "query_string": b""})


def _body(resp):
    return resp.status_code, json.loads(resp.body)


@pytest.fixture
def hosted(monkeypatch):
    import widgets.navegador.owner  # noqa: F401 — the login package is imported through its owner
    from server import daemon_api
    from widgets.navegador.owner_login import relay_link
    monkeypatch.setattr(daemon_api, "_is_cloud", lambda: True)
    monkeypatch.setattr(relay_link, "_is_cloud", lambda: True)
    monkeypatch.setenv("CONTROL_PLANE_URL", "https://service.test")
    calls: list = []

    async def _http(method, path, body=None, *, timeout=0):
        calls.append((method, path))
        if path == "/daemon/pairing-code":
            return 200, {"code": "ABCD-EFGH", "expires_at": "2026-11-09T10:10:00Z"}
        if path == "/daemon/presence":
            return 200, {"connected": True, "caps": ["files.list", "browser.auth"], "version": "0.3.0",
                         "platform": "windows", "since": "2026-11-09T10:00:00Z"}
        if path == "/daemon/credentials":
            return 200, {"credentials": [{"id": "x", "revoked_at": None}]}
        return 404, {}
    monkeypatch.setattr(relay_link, "_http", _http)
    return daemon_api, calls


def test_a_hosted_engine_returns_a_pairing_code(hosted):
    api, calls = hosted
    code, body = _body(asyncio.run(api.daemon_pair(_req())))
    assert code == 200 and body == {"ok": True, "mode": "relay", "code": "ABCD-EFGH",
                                    "expires_at": "2026-11-09T10:10:00Z"}, body
    assert ("POST", "/daemon/pairing-code") in calls


def test_a_cross_site_page_cannot_mint_a_code(hosted):
    api, calls = hosted
    code, body = _body(asyncio.run(api.daemon_pair(_req(origin="https://evil.example"))))
    assert code == 403 and body["error"] == "cross_origin" and not calls


def test_a_cloud_engine_without_a_relay_says_so(hosted, monkeypatch):
    api, calls = hosted
    monkeypatch.delenv("CONTROL_PLANE_URL")
    code, body = _body(asyncio.run(api.daemon_pair(_req())))
    assert code == 409 and body["error"] == "relay_not_available" and not calls


def test_the_status_carries_what_the_relay_sees(hosted):
    api, _ = hosted
    code, body = _body(asyncio.run(api.daemon_status(_req())))
    assert code == 200 and body["state"] == "remote"
    assert body["relay"] == {"paired": True, "connected": True, "caps": ["files.list", "browser.auth"],
                             "version": "0.3.0", "platform": "windows", "since": "2026-11-09T10:00:00Z"}


def test_a_local_engine_reports_no_relay(monkeypatch):
    from server import daemon_api
    monkeypatch.setattr(daemon_api, "_is_cloud", lambda: False)
    monkeypatch.setattr(daemon_api, "_daemon_config", lambda: {})
    code, body = _body(asyncio.run(daemon_api.daemon_status(_req(host="127.0.0.1:43917"))))
    assert body["relay"] == {"paired": False, "connected": False, "caps": [], "version": "", "platform": "",
                             "since": None}
