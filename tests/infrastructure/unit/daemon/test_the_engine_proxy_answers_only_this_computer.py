"""The engine's `/api/daemon/*` proxy answers status and pairing, and refuses a caller that is not on this computer
(V2-575 P1).

`server/api_guard.py` lets a caller with `ZAELAR_API_TOKEN` through from the network — right for reading his agent
from another device, wrong for routes that ACT ON THIS DESKTOP (grant a folder, open the folder dialog, start a
process, pair). So the daemon's routes ask the narrower question themselves: is the peer loopback? A caller off this
computer still learns from `status` THAT the daemon is connected, never which folders he granted. Pairing over
loopback needs no code (decision 6); a cloud engine says the relay is not there instead of minting one.

The daemon is faked at the proxy's one HTTP seam (`_call`); the routes are called with real Starlette requests whose
peer is set by the test. Disarm: `_on_this_machine` answering True for every peer → red.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from starlette.requests import Request


def _req(peer: str, *, origin: str = "", method: str = "POST") -> Request:
    headers = [(b"host", b"127.0.0.1:43917")]
    if origin:
        headers.append((b"origin", origin.encode()))
    return Request({"type": "http", "method": method, "path": "/api/daemon/x", "headers": headers,
                    "client": (peer, 50000), "query_string": b""})


@pytest.fixture
def proxy(monkeypatch):
    from server import daemon_api
    calls: list = []

    async def _call(cfg, path, payload=None, *, timeout=4.0):
        calls.append(path)
        if path == "/health":
            return 200, {"ok": True, "version": "0.2.2", "configured": True,
                         "capabilities": ["files.list", "browser.auth"]}
        if path == "/permissions":
            return 200, {"ok": True, "roots": ["/Users/x/Documents"], "candidates": []}
        return 200, {"ok": True, "roots": ["/Users/x/Documents"]}
    monkeypatch.setattr(daemon_api, "_call", _call)
    monkeypatch.setattr(daemon_api, "_daemon_config", lambda: {"token": "t", "port": 45817})
    monkeypatch.setattr(daemon_api, "_is_cloud", lambda: False)
    monkeypatch.setattr(daemon_api, "_daemon_version", lambda: "0.2.2")
    return daemon_api, calls


def _body(resp):
    return resp.status_code, json.loads(resp.body)


def test_status_on_this_computer_carries_the_folders_and_the_capabilities(proxy):
    api, _ = proxy
    code, body = _body(asyncio.run(api.daemon_status(_req("127.0.0.1", method="GET"))))
    assert code == 200 and body["reachable"] and body["state"] == "ok"
    assert body["roots"] == ["/Users/x/Documents"] and "browser.auth" in body["capabilities"]


def test_status_off_this_computer_says_connected_but_never_the_paths(proxy):
    api, _ = proxy
    code, body = _body(asyncio.run(api.daemon_status(_req("192.168.1.40", method="GET"))))
    assert code == 200 and body["reachable"], "a phone on his network may know his computer is connected"
    assert body["roots"] == [] and body["candidates"] == [], f"…and never which folders: {body['roots']}"
    assert body["state"] == "ok", "the colour is the same judgement wherever it is read from"


@pytest.mark.parametrize("route", ["daemon_grant", "daemon_revoke", "daemon_pick"])
def test_acting_routes_refuse_a_caller_off_this_computer(proxy, route):
    api, calls = proxy
    code, body = _body(asyncio.run(getattr(api, route)(_req("192.168.1.40"), {"path": "/Users/x/Documents"})))
    assert code == 403 and body["error"] == "not_on_this_computer", (code, body)
    assert not [c for c in calls if c.startswith("/permissions/")], "the daemon was never asked"
    code, body = _body(asyncio.run(getattr(api, route)(_req("127.0.0.1"), {"path": "/Users/x/Documents"})))
    assert code == 200 and body["ok"], "on this computer it goes through"


def test_start_refuses_a_caller_off_this_computer(proxy):
    api, _ = proxy
    code, body = _body(asyncio.run(api.daemon_start(_req("10.0.0.7"))))
    assert code == 403 and body["error"] == "not_on_this_computer"


def test_a_cross_site_page_is_still_refused_on_loopback(proxy):
    api, _ = proxy
    code, body = _body(asyncio.run(api.daemon_grant(_req("127.0.0.1", origin="https://evil.example"), {"path": "/x"})))
    assert code == 403 and body["error"] == "cross_origin"


def test_pairing_over_loopback_needs_no_code(proxy):
    api, _ = proxy
    code, body = _body(asyncio.run(api.daemon_pair(_req("127.0.0.1"))))
    assert code == 200 and body == {"ok": True, "paired": True, "mode": "loopback", "code": None}
    code, body = _body(asyncio.run(api.daemon_pair(_req("192.168.1.40"))))
    assert code == 403 and body["error"] == "not_on_this_computer"


def test_pairing_from_the_cloud_says_the_relay_is_not_there(proxy, monkeypatch):
    api, _ = proxy
    monkeypatch.setattr(api, "_is_cloud", lambda: True)
    code, body = _body(asyncio.run(api.daemon_pair(_req("127.0.0.1"))))
    assert code == 409 and body["error"] == "relay_not_available"


def test_pairing_with_no_daemon_installed_says_so(proxy, monkeypatch):
    api, _ = proxy
    monkeypatch.setattr(api, "_daemon_config", lambda: {})
    code, body = _body(asyncio.run(api.daemon_pair(_req("127.0.0.1"))))
    assert code == 409 and body["error"] == "not_installed"


def test_the_router_is_mounted_on_the_app():
    from server import daemon_api
    paths = {r.path for r in daemon_api.router.routes}
    assert {"/api/daemon/status", "/api/daemon/pair", "/api/daemon/permissions/grant"} <= paths
