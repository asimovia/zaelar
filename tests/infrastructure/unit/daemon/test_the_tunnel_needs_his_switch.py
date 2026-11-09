"""The egress tunnel runs only while HE has it switched on, on his computer, and stops the moment he switches it off
(V2-836).

Off by default; a hand-edited `"enabled": true` without a recorded consent reads as off; ON needs consent; a remote
command can OFFER a tunnel but never switch it — `egress.offer` is refused `egress_disabled` while it is off, and the
`hello` the relay sees carries `egress` only while it is on. Mid-session, switching off closes the tunnel AND every
stream on it, and a stream asked afterwards is refused.

The engine end is a real WebSocket server on an ephemeral loopback port; the daemon's state lives in a temp workspace.
Disarms (seen red 2026-11-09): `_clean_egress` trusting `enabled` without `consented_at` → red; the switch check
removed from `Tunnel.offer` → the offer case red; `capabilities()` always adding `egress` → the hello case red;
`switch()` not stopping the tunnel AND the loop not re-reading the switch → the mid-session case red (either one alone
still closes it: two paths on purpose).
"""
from __future__ import annotations

import base64
import json
import queue
import socket
import threading
import time

import pytest
from websockets.sync.server import serve


@pytest.fixture
def ws_root(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    monkeypatch.delenv("ZAELAR_DAEMON_RELAY_URL", raising=False)
    from daemon import config as dcfg
    dcfg.reset_cache()
    yield tmp_path
    dcfg.reset_cache()


def _wait(cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


# ── the switch itself ──────────────────────────────────────────────────────────────────────────────────────────

def test_off_by_default_and_on_only_with_consent(ws_root):
    from daemon import config
    assert config.egress() == {"enabled": False, "consented_at": None}
    with pytest.raises(ValueError):
        config.save_egress(True)
    assert not config.egress_enabled()
    on = config.save_egress(True, consent=True)
    assert on["enabled"] and isinstance(on["consented_at"], int)
    off = config.save_egress(False)
    assert not off["enabled"] and off["consented_at"] == on["consented_at"], "off keeps when he once consented"


def test_a_hand_edited_file_cannot_switch_it_on(ws_root):
    from daemon import config
    config.load()
    path = ws_root / "config" / "daemon" / "daemon.json"
    data = json.loads(path.read_text())
    data["egress"] = {"enabled": True}
    path.write_text(json.dumps(data))
    config.reset_cache()
    assert not config.egress_enabled(), "enabled without a recorded consent is off"


def test_an_offer_is_refused_while_the_switch_is_off(ws_root):
    from daemon.relay import dispatch
    out = dispatch.handle({"t": "command", "id": "c1", "op": "egress.offer",
                           "args": {"token": "inst.abcdefghijklmnopqrstuvwxyz", "url": "wss://my.example.com/daemon/tunnel",
                                    "expires_at": int(time.time()) + 300}})
    assert out["ok"] is False and out["error"]["code"] == "egress_disabled", out


def test_hello_carries_egress_only_while_it_is_on(ws_root):
    from daemon import config
    from daemon.http import routes
    assert "egress" not in routes.capabilities()
    config.save_egress(True, consent=True)
    assert "egress" in routes.capabilities()


def test_the_loopback_route_never_switches_on_for_the_relay(ws_root):
    from daemon import config
    from daemon.fs.refusal import Refusal
    from daemon.http import routes

    class Req:
        def __init__(self, who):
            self.who = who

        def _caller(self):
            return self.who
    with pytest.raises(Refusal) as r:
        routes.egress_switch(Req("relay"), {"enabled": True, "consent": True})
    assert r.value.code == "not_local" and not config.egress_enabled()
    with pytest.raises(Refusal) as r:
        routes.egress_switch(Req("local"), {"enabled": True})
    assert r.value.code == "consent_required"
    out = routes.egress_switch(Req("local"), {"enabled": True, "consent": True})
    assert out["enabled"] is True and out["consented_at"]
    assert routes.egress_switch(Req("relay"), {"enabled": False})["enabled"] is False, "off is allowed from anywhere"


def test_an_offer_names_only_a_tunnel_on_the_relays_site(ws_root):
    from daemon.egress.tunnel import acceptable_url
    relay = "https://api.zaelar.example"
    assert acceptable_url("wss://my.zaelar.example/daemon/tunnel", relay)
    assert not acceptable_url("ws://my.zaelar.example/daemon/tunnel", relay), "never in clear to the network"
    assert not acceptable_url("wss://attacker.example/daemon/tunnel", relay)
    assert not acceptable_url("wss://127.0.0.1:9/daemon/tunnel", relay)
    assert acceptable_url("ws://127.0.0.1:9/daemon/tunnel", "http://127.0.0.1:8")


# ── mid-session: the kill switch ───────────────────────────────────────────────────────────────────────────────

class FakeEngine:
    """The engine end of the tunnel: accepts the dial, records frames, lets the test send `open`/`data`."""

    def __init__(self):
        self.frames: queue.Queue = queue.Queue()
        self.conns: list = []
        self.auth: list = []
        self.ended = threading.Event()
        self._server = serve(self._handler, "127.0.0.1", 0)
        self.port = self._server.socket.getsockname()[1]
        self.url = f"ws://127.0.0.1:{self.port}/daemon/tunnel"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def _handler(self, ws):
        self.auth.append(dict(ws.request.headers.raw_items()).get("Authorization"))
        self.conns.append(ws)
        try:
            for raw in ws:
                self.frames.put(json.loads(raw))
        except Exception:   # noqa: BLE001
            pass
        self.ended.set()

    def send(self, frame):
        self.conns[-1].send(json.dumps(frame))

    def next(self, kind, timeout=5.0):
        end = time.time() + timeout
        while time.time() < end:
            try:
                f = self.frames.get(timeout=0.1)
            except queue.Empty:
                continue
            if f.get("t") == kind:
                return f
        raise AssertionError(f"no {kind} frame")

    def close(self):
        self._server.shutdown()


def test_switching_off_mid_session_closes_the_tunnel_and_every_stream(ws_root, monkeypatch):
    from daemon import config
    from daemon.egress import tunnel as tmod
    from daemon.security import egress_guard as guard

    config.save_egress(True, consent=True)
    engine = FakeEngine()
    pairs: list = []

    def opener(host, port):
        if not config.egress_enabled():
            raise guard.Refused("egress_disabled")
        a, b = socket.socketpair()
        pairs.append(b)
        return a, host

    t = tmod.Tunnel(opener=opener, relay_url="http://127.0.0.1:1")
    try:
        token = "inst." + "x" * 43
        out = t.offer({"token": token, "url": engine.url, "expires_at": time.time() + 120})
        assert out["accepted"]
        assert _wait(lambda: t.connected()), t.status
        assert engine.auth[-1] == f"Bearer {token}"
        engine.send({"t": "open", "id": 1, "host": "www.example.com", "port": 443})
        engine.next("ok")
        engine.send({"t": "data", "id": 1, "b64": base64.b64encode(b"hello").decode()})
        assert pairs[0].recv(5) == b"hello"
        pairs[0].sendall(b"back")
        assert base64.b64decode(engine.next("data")["b64"]) == b"back"

        monkeypatch.setattr(tmod, "TUNNEL", t)   # `switch` stops the module's tunnel: point it at this one
        tmod.switch(False)
        assert _wait(lambda: engine.ended.is_set()), "the tunnel socket closed"
        assert not t.connected() and t.streams() == 0
        pairs[0].settimeout(2)
        assert pairs[0].recv(10) == b"", "the stream's socket was closed too"
        with pytest.raises(Exception):
            t.offer({"token": token, "url": engine.url, "expires_at": time.time() + 120})
    finally:
        t.stop()
        engine.close()
