"""The engine always starts on the same ports, on this machine only (2026-10-21).

The voice worker's health server took LiveKit's dev default — port 0 on every interface — so each start opened a
NEW random port reachable from the local network, which `./zaelar stop` could not name and `status` could not show:
a dead instance's port went unnoticed. It is now fixed at app port + 1000, bound to 127.0.0.1, and in the PORTS list
that `stop` frees.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]


def _launcher():
    spec = importlib.util.spec_from_file_location("zaelar_launcher", ENGINE / "scripts" / "zaelar.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_worker_health_server_is_fixed_and_loopback(monkeypatch):
    from voice.engine.pipeline import agent
    seen = {}

    class _Server:
        def __init__(self, **kw):
            seen.update(kw)

        def rtc_session(self, *a, **k):
            return None

    monkeypatch.setattr(agent, "AgentServer", _Server)
    monkeypatch.delenv("ZAELAR_WORKER_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    agent.make_server()
    assert seen.get("host") == "127.0.0.1", "the worker's health server answered on every interface"
    assert seen.get("port") == 44917, f"not the fixed port: {seen.get('port')!r} (0 means random)"


def test_it_follows_the_app_port_and_an_explicit_override(monkeypatch):
    from voice.engine.pipeline import agent
    monkeypatch.delenv("ZAELAR_WORKER_PORT", raising=False)
    monkeypatch.setenv("PORT", "43921")
    assert agent.worker_health_port() == 44921, "a second instance on another app port must not collide"
    monkeypatch.setenv("ZAELAR_WORKER_PORT", "50001")
    assert agent.worker_health_port() == 50001


def test_stop_and_status_know_every_port_the_engine_opens():
    ports = {p for p, _ in _launcher().PORTS}
    assert {43917, 44917} <= ports, "a port `stop` does not name survives every stop"
