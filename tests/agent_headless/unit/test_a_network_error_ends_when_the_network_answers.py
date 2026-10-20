"""A network-class failure is a fact about the CONNECTION, not the provider (2026-10-20).

A Wi-Fi switch took DNS down; memory consolidation failed at session close with «[Errno 8] nodename nor
servname»; the network came back seconds later and the heart card stayed red for the whole 600 s TTL, because only
a later memory call could clear it. The status now re-checks every network-class record against the network.
"""
from __future__ import annotations

import pytest

from voice import health_state

DNS = "rem: sin proveedor (deepseek-flash: [Errno 8] nodename nor servname provided, or not known)"


@pytest.fixture(autouse=True)
def _clean():
    health_state._errors.clear()
    yield
    health_state._errors.clear()


def test_a_dns_failure_is_dropped_once_the_network_answers():
    health_state.record("memory", "outage", DNS)
    assert health_state.revalidate_network(lambda: True) == 1
    assert health_state.get("memory") is None


def test_it_stays_while_the_network_is_still_down():
    health_state.record("memory", "outage", DNS)
    assert health_state.revalidate_network(lambda: False) == 0
    assert health_state.get("memory")["cls"] == "network"


@pytest.mark.parametrize("svc,text", [
    ("llm", "402 Payment Required — insufficient balance"),
    ("tts", "401 invalid api key"),
    ("memory", "insight rejected: empty"),
])
def test_a_provider_failure_is_not_cleared_by_the_network(svc, text):
    """A balance, a key or our own bug is not a connection: a working network proves nothing about them."""
    health_state.record(svc, "outage", text)
    assert health_state.revalidate_network(lambda: True) == 0
    assert health_state.get(svc) is not None


def test_the_probe_is_not_run_when_there_is_nothing_to_revalidate():
    health_state.record("llm", "auth", "401 unauthorized")
    calls = []
    health_state.revalidate_network(lambda: calls.append(1) or True)
    assert calls == [], "a polling panel must not become a probe loop"


def test_the_probe_asks_the_hosts_the_model_table_declares(monkeypatch):
    from nucleo import net_probe
    asked = []

    class _Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def _connect(addr, timeout):
        asked.append(addr)
        return _Conn()

    monkeypatch.setattr(net_probe.socket, "create_connection", _connect)
    monkeypatch.setitem(net_probe._cache, "at", 0.0)
    assert net_probe.back() is True
    hosts = {h for h, _ in asked}
    assert hosts == set(net_probe._hosts()) and hosts, "every declared remote host, none invented"
    assert all(port == 443 for _, port in asked)


def test_one_provider_refusing_while_the_rest_answer_is_NOT_the_network_back(monkeypatch):
    """«connection refused» from one provider is that provider down: clearing it would hide a real outage."""
    from nucleo import net_probe

    class _Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    down = net_probe._hosts()[0]

    def _connect(addr, timeout):
        if addr[0] == down:
            raise ConnectionRefusedError(down)
        return _Conn()

    monkeypatch.setattr(net_probe.socket, "create_connection", _connect)
    monkeypatch.setitem(net_probe._cache, "at", 0.0)
    assert net_probe.back() is False


def test_the_status_route_revalidates_before_reading():
    """WIRING: the fix is useless if the status never calls it."""
    src = open("server/voice_api.py", encoding="utf8").read()
    assert "revalidate_network" in src and "net_probe.back" in src
