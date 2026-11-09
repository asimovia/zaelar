"""The daemon dials OUT to the relay, says hello, runs relayed commands through the loopback handlers and obeys `bye`
(V2-575 P3).

A remote engine cannot reach his loopback, so a paired daemon opens an outbound WebSocket with its credential, sends
`hello {v:1, caps, version, platform}` first, and then answers `ping` with `pong` and each `command` with one `result`.
What a remote caller may NOT do is enforced at the relay boundary: `profile` never reaches `browser.open`, an unknown op
is an error, a `deadline_ms` is honoured and a result over 20 MB is refused. `bye revoked` forgets the credential and
stops; `bye replaced` stops and keeps it; `bye shutdown` reconnects, after a jittered backoff from 1 s to 60 s.

The relay is a real WebSocket server on an ephemeral loopback port (`fake_relay.py`); the daemon's state lives in a
temporary workspace.
Disarms: `strip_remote` passing `profile` through → red; `bye revoked` not forgetting → red; the deadline not
enforced → red.
"""
from __future__ import annotations

import json
import os
import random
import stat
import time

import pytest

from tests.infrastructure.unit.daemon.fake_relay import FakeRelay


@pytest.fixture
def ws_root(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    monkeypatch.delenv("ZAELAR_DAEMON_RELAY_URL", raising=False)
    from daemon import config as dcfg
    dcfg.reset_cache()
    yield tmp_path
    dcfg.reset_cache()


def _pair(url: str, credential: str = "c" * 40) -> None:
    from daemon.relay import config
    config.store_pairing(credential, relay_url=url, account_hint="a…@…")


def _client(**kw):
    from daemon.relay import client
    return client.RelayClient(**kw)


def _wait(cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


# ── the file ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_relay_json_is_private_and_apart_from_daemon_json(ws_root):
    from daemon.relay import config
    _pair("https://relay.example")
    f = ws_root / "config" / "daemon" / "relay.json"
    assert f.exists() and not (ws_root / "config" / "daemon" / "daemon.json").exists()
    if os.name != "nt":
        assert stat.S_IMODE(f.stat().st_mode) == 0o600
    assert config.paired() and config.url() == "https://relay.example"


def test_the_credential_never_travels_in_clear_to_the_network(ws_root, monkeypatch):
    from daemon.relay import config
    assert config.acceptable("https://relay.example") and config.acceptable("http://127.0.0.1:9")
    assert not config.acceptable("http://relay.example") and not config.acceptable("ftp://relay.example")
    monkeypatch.setenv("ZAELAR_DAEMON_RELAY_URL", "http://relay.example")
    assert config.url() == "", "a cleartext relay off this machine is no relay at all"
    monkeypatch.setenv("ZAELAR_DAEMON_RELAY_URL", "https://env.example")
    _pair("https://file.example")
    assert config.url() == "https://env.example", "the environment wins over the file"
    assert config.ws_url("https://h.example/p") == "wss://h.example/p/daemon/relay"


def test_an_unpaired_daemon_never_dials(ws_root):
    c = _client()
    assert c.start() is False and c.status["state"] == "idle"


# ── the handshake, ping and bye ─────────────────────────────────────────────────────────────────────────────

def test_hello_is_the_first_frame_and_welcome_connects(ws_root):
    relay = FakeRelay()
    try:
        _pair(relay.url, "k" * 40)
        c = _client()
        assert c.start()
        assert relay.connected.wait(10) and _wait(c.connected)
        conn = relay.conns[0]
        assert conn.headers.get("authorization") == "Bearer " + "k" * 40
        hello = conn.hello
        assert hello["t"] == "hello" and hello["v"] == 1 and hello["platform"] in ("macos", "windows", "linux")
        assert "files.list" in hello["caps"] and hello["version"]
        conn.send({"t": "ping"})
        assert conn.inbox.get(timeout=5) == {"t": "pong"}
        c.stop()
        c.join(5)
    finally:
        relay.close()


def test_bye_revoked_forgets_the_credential_and_stops(ws_root):
    from daemon.relay import config
    relay = FakeRelay(on_connect=lambda conn: conn.send({"t": "bye", "reason": "revoked"}))
    try:
        _pair(relay.url)
        c = _client()
        c.start()
        c.join(10)
        assert c.stopped_by == "revoked" and c.status["state"] == "revoked"
        assert config.credential() == "", "a revoked daemon must not keep a dead credential"
        assert config.url() == relay.url, "the relay address is kept for the next pairing"
        assert len(relay.conns) == 1, "a revoked daemon does not dial again"
    finally:
        relay.close()


def test_bye_replaced_stops_without_forgetting(ws_root):
    from daemon.relay import config
    relay = FakeRelay(on_connect=lambda conn: conn.send({"t": "bye", "reason": "replaced"}))
    try:
        _pair(relay.url)
        c = _client()
        c.start()
        c.join(10)
        assert c.stopped_by == "replaced" and config.credential()
        assert len(relay.conns) == 1
    finally:
        relay.close()


def test_bye_shutdown_reconnects_after_a_backoff(ws_root):
    sleeps: list = []
    relay = FakeRelay(on_connect=lambda conn: conn.send({"t": "bye", "reason": "shutdown"})
                      if len(relay.conns) == 1 else None)
    try:
        _pair(relay.url)
        c = _client(sleep=lambda s: sleeps.append(s), rng=random.Random(1))
        c.start()
        assert _wait(lambda: len(relay.conns) >= 2), "after a shutdown bye the daemon dials again"
        assert sleeps and 0.5 <= sleeps[0] <= 1.0, sleeps
        c.stop()
        c.join(5)
    finally:
        relay.close()


def test_the_backoff_doubles_from_one_second_and_stops_at_sixty():
    from daemon.relay import client
    rng = random.Random(7)
    for attempt, ceiling in [(0, 1), (1, 2), (2, 4), (5, 32), (6, 60), (20, 60)]:
        for _ in range(20):
            d = client.backoff(attempt, rng)
            assert ceiling / 2 <= d <= ceiling, (attempt, d)


def test_a_refused_handshake_retries_with_a_growing_delay(ws_root):
    sleeps: list = []
    relay = FakeRelay(status=503)
    try:
        _pair(relay.url)
        c = _client(sleep=lambda s: (sleeps.append(s), c.stop() if len(sleeps) >= 4 else None),
                    rng=random.Random(3))
        c.start()
        c.join(10)
        assert len(sleeps) == 4 and sleeps[3] > sleeps[0], sleeps
        assert c.status["last_error"] == "handshake 503"
    finally:
        relay.close()


# ── what a remote caller may do ─────────────────────────────────────────────────────────────────────────────

def test_profile_never_crosses_the_relay(ws_root, monkeypatch):
    from daemon.http import routes
    from daemon.relay import dispatch
    seen: list = []
    monkeypatch.setattr(routes, "browser_open", lambda req, payload: seen.append((req._caller(), payload)) or
                        {"ok": True, "task": payload["task"], "open": True})
    out = dispatch.handle({"t": "command", "id": "1", "op": "browser.open",
                           "args": {"url": "https://shop.example/login", "task_id": "t1",
                                    "profile": "/Users/him/Library/Chrome"}})
    assert out["ok"] and out["data"]["opened"] is True
    assert seen == [("relay", {"url": "https://shop.example/login", "task": "t1"})], seen


def test_an_unknown_op_is_an_error_result_over_the_wire(ws_root):
    relay = FakeRelay()
    try:
        _pair(relay.url)
        c = _client()
        c.start()
        assert relay.connected.wait(10) and _wait(c.connected)
        res = relay.conns[0].command("shell.exec", {"cmd": "id"})
        assert res["ok"] is False and res["error"]["code"] == "unknown_op", res
        res = relay.conns[0].command("daemon.status")
        assert res["ok"] and res["data"]["version"] and "caps" in res["data"], res
        c.stop()
        c.join(5)
    finally:
        relay.close()


def test_the_deadline_is_honoured(ws_root, monkeypatch):
    from daemon.relay import dispatch
    monkeypatch.setitem(dispatch.OPS, "daemon.status", lambda args: time.sleep(3) or {"ok": True})
    t0 = time.time()
    out = dispatch.handle({"id": "d", "op": "daemon.status", "args": {}, "deadline_ms": 200})
    assert out["ok"] is False and out["error"]["code"] == "deadline_exceeded"
    assert time.time() - t0 < 2, "the answer comes at the deadline, not when the work ends"


def test_a_result_over_twenty_megabytes_is_refused(ws_root, monkeypatch):
    from daemon.relay import dispatch
    monkeypatch.setattr(dispatch, "MAX_RESULT_BYTES", 1000)
    monkeypatch.setitem(dispatch.OPS, "daemon.status", lambda args: {"ok": True, "blob": "x" * 2000})
    out = dispatch.handle({"id": "big", "op": "daemon.status", "args": {}})
    assert out["error"]["code"] == "result_too_large" and "blob" not in json.dumps(out)


def test_a_refusal_crosses_with_its_code(ws_root):
    from daemon.relay import dispatch
    out = dispatch.handle({"id": "r", "op": "files.read", "args": {"path": "/etc/passwd"}})
    assert out["ok"] is False and out["error"]["code"] not in ("internal", "unknown_op"), out


# ── pairing and the login link ──────────────────────────────────────────────────────────────────────────────

def test_pairing_stores_the_credential_from_a_one_time_code(ws_root, monkeypatch):
    from daemon.relay import config, pair
    calls: list = []
    monkeypatch.setattr(pair, "POST", lambda url, body: calls.append((url, body)) or
                        (200, {"credential": "z" * 48, "account_hint": "r…@…", "relay_url": "https://relay.example"}))
    out = pair.pair("abcd efgh", "https://relay.example")
    assert calls[0][0] == "https://relay.example/daemon/pair" and calls[0][1]["code"] == "ABCD-EFGH"
    dev = calls[0][1]["device"]
    assert set(dev) == {"platform", "version", "hostname_hash"} and len(dev["hostname_hash"]) == 16
    assert config.credential() == "z" * 48 and out["account_hint"] == "r…@…"
    with pytest.raises(pair.PairingError) as e:
        pair.pair("nope")
    assert e.value.code == "bad_code"
    monkeypatch.setattr(pair, "POST", lambda url, body: (410, {}))
    with pytest.raises(pair.PairingError) as e:
        pair.pair("ABCD-EFGH", "https://relay.example")
    assert e.value.code == "rejected"


def test_the_login_link_is_optional(ws_root, monkeypatch):
    from daemon.relay import login_link
    assert login_link.login_link() is None, "not paired: no link"
    _pair("https://relay.example", "q" * 40)
    seen: list = []
    monkeypatch.setattr(login_link, "GET", lambda url, cred: seen.append((url, cred)) or (404, {}))
    assert login_link.login_link() is None
    monkeypatch.setattr(login_link, "GET", lambda url, cred: (200, {"url": "https://my.example/x?t=1",
                                                                   "expires_at": "2026-11-09T00:05:00Z"}))
    assert login_link.login_link() == {"url": "https://my.example/x?t=1", "expires_at": "2026-11-09T00:05:00Z"}
    assert seen == [("https://relay.example/daemon/login-link", "q" * 40)]
