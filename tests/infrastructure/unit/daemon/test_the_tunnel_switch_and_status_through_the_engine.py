"""The engine's face of the tunnel (V2-836): `/api/daemon/status.egress` and `POST /api/daemon/egress`.

`status.egress = {capable, enabled, connected, hosts_last_hour}` is always present (all-false when nothing is known).
On this computer it is the daemon's own answer (`GET /egress`); away from his computer it is what his daemon declares
through the relay (`egress` in its capabilities = he switched it on) plus this engine's own tunnel. The switch goes to
the daemon ONLY from an engine on his computer, over loopback, and an ON always carries `consent: true` from the
screen's button; an engine away from his computer answers `409 switch_on_his_computer`, because no remote command
switches the tunnel.

The daemon is faked at the engine's one loopback seam (`daemon_api._call`), the relay at `relay_link._http`.
Disarm (seen red 2026-11-09): the cloud branch removed from the switch route (it forwards like a local one) → red.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from starlette.requests import Request


def _req(*, host: str = "agent.example", client: str = "127.0.0.1", path="/api/daemon/egress") -> Request:
    return Request({"type": "http", "method": "POST", "path": path, "headers": [(b"host", host.encode())],
                    "client": (client, 50000), "query_string": b""})


def _body(resp):
    return resp.status_code, json.loads(resp.body)


@pytest.fixture
def local(monkeypatch):
    from server import daemon_api
    calls: list = []
    state = {"enabled": False}

    async def _call(cfg, path, payload=None, *, timeout=0):
        calls.append((path, payload))
        if path == "/health":
            return 200, {"ok": True, "version": "0.2.3", "configured": True, "capabilities": ["files.list"]}
        if path == "/permissions":
            return 200, {"ok": True, "roots": ["/x"], "candidates": []}
        if path == "/egress" and payload is None:
            return 200, {"ok": True, **state, "connected": state["enabled"], "hosts_last_hour": 3, "state": "idle"}
        if path == "/egress":
            if payload.get("enabled") and not payload.get("consent"):
                return 403, {"ok": False, "error": "consent_required"}
            state["enabled"] = bool(payload.get("enabled"))
            return 200, {"ok": True, **state}
        return 404, {}
    monkeypatch.setattr(daemon_api, "_is_cloud", lambda: False)
    monkeypatch.setattr(daemon_api, "_daemon_config", lambda: {"token": "t" * 64, "port": 45817})
    monkeypatch.setattr(daemon_api, "_call", _call)
    return daemon_api, calls, state


def test_local_status_carries_the_daemons_own_answer(local):
    api, _calls, state = local
    code, body = _body(asyncio.run(api.daemon_status(_req(path="/api/daemon/status"))))
    assert code == 200 and body["egress"] == {"capable": True, "enabled": False, "connected": False,
                                              "hosts_last_hour": 3}


def test_local_switch_passes_consent_only_for_on(local):
    api, calls, state = local
    code, body = _body(asyncio.run(api.daemon_egress(_req(), {"enabled": True, "consent": True})))
    assert code == 200 and state["enabled"] and calls[-1] == ("/egress", {"enabled": True, "consent": True})
    code, _ = _body(asyncio.run(api.daemon_egress(_req(), {"enabled": False, "consent": True})))
    assert code == 200 and not state["enabled"] and calls[-1] == ("/egress", {"enabled": False, "consent": False})
    code, body = _body(asyncio.run(api.daemon_egress(_req(), {"enabled": True})))
    assert code == 403 and body["error"] == "consent_required" and not state["enabled"]


def test_the_switch_refuses_a_caller_off_this_computer(local):
    api, calls, state = local
    code, body = _body(asyncio.run(api.daemon_egress(_req(client="10.0.0.7"), {"enabled": True, "consent": True})))
    assert code == 403 and not state["enabled"] and not calls


def test_an_engine_away_from_his_computer_never_switches_it(monkeypatch):
    from server import daemon_api
    sent: list = []

    async def _call(*a, **k):
        sent.append(a)
        return 200, {"ok": True}
    monkeypatch.setattr(daemon_api, "_is_cloud", lambda: True)
    monkeypatch.setattr(daemon_api, "_call", _call)
    code, body = _body(asyncio.run(daemon_api.daemon_egress(_req(client="10.0.0.7"),
                                                            {"enabled": True, "consent": True})))
    assert code == 409 and body["error"] == "switch_on_his_computer" and not sent


def test_remote_status_reads_his_daemons_capabilities(monkeypatch):
    import widgets.navegador.owner  # noqa: F401
    from nucleo.daemon_egress import link
    from server import daemon_api
    from widgets.navegador.owner_login import relay_link
    link.reset_for_tests()
    monkeypatch.setattr(daemon_api, "_is_cloud", lambda: True)
    monkeypatch.setattr(relay_link, "_is_cloud", lambda: True)
    monkeypatch.setenv("CONTROL_PLANE_URL", "https://service.test")
    caps = {"now": ["files.list", "browser.auth", "egress"]}

    async def _http(method, path, body=None, *, timeout=0):
        if path == "/daemon/presence":
            return 200, {"connected": True, "caps": caps["now"], "version": "0.2.3", "platform": "macos"}
        if path == "/daemon/credentials":
            return 200, {"credentials": [{"id": "x"}]}
        return 404, {}
    monkeypatch.setattr(relay_link, "_http", _http)
    body = json.loads(asyncio.run(daemon_api.daemon_status(_req(path="/api/daemon/status"))).body)
    assert body["egress"] == {"capable": True, "enabled": True, "connected": False, "hosts_last_hour": 0}
    caps["now"] = ["files.list"]
    body = json.loads(asyncio.run(daemon_api.daemon_status(_req(path="/api/daemon/status"))).body)
    assert body["egress"]["capable"] and not body["egress"]["enabled"], "a recent daemon, switched off"


def test_status_always_has_the_field(monkeypatch):
    from server import daemon_api
    monkeypatch.setattr(daemon_api, "_is_cloud", lambda: False)
    monkeypatch.setattr(daemon_api, "_daemon_config", lambda: {})
    body = json.loads(asyncio.run(daemon_api.daemon_status(_req(path="/api/daemon/status"))).body)
    assert body["egress"] == {"capable": False, "enabled": False, "connected": False, "hosts_last_hour": 0}
