"""Offer → dial → CONNECT → bytes back: the egress tunnel end to end, the real daemon against the real engine route
(V2-836).

The ENGINE is the real `/daemon/tunnel` route and `nucleo.daemon_egress` (token set, `mux.Session`, the local
forwarder) under uvicorn on an ephemeral loopback port, with an instance id in its environment. The DAEMON is the real
`daemon.egress.tunnel.Tunnel` reached through the real relay dispatcher (`egress.offer`). The relay between them is
a function call. Only the destination is faked: the daemon's opener connects to a local echo server (the real guard
would — rightly — refuse a loopback destination), and records what it was asked for.

Also here: the token (prefix, constant-time verify, expiry, a token of another instance) and one `Session`
multiplexing two streams over one fake socket without mixing their bytes.

Disarms (seen red 2026-11-09): `tokens.verify` ignoring the expiry → the expired case red; `mux` routing every `data`
frame to the first stream → the two-streams case red; the forwarder answering CONNECT without opening a stream →
the end-to-end case red.
"""
from __future__ import annotations

import asyncio
import socket
import threading
import time

import pytest


def _wait(cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


# ── the token ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_token_names_its_instance_and_only_that_instance_accepts_it():
    from nucleo.daemon_egress import tokens
    tokens.forget_all()
    tok, exp = tokens.mint(instance="m1abc", now=1000.0, ttl=60)
    head, _, secret = tok.partition(".")
    assert head == "m1abc" and len(secret) >= 43 and "=" not in secret and exp == 1060.0
    assert tokens.prefix(tok) == "m1abc"
    assert tokens.verify(tok, instance="m1abc", now=1030.0)
    assert not tokens.verify(tok, instance="m2other", now=1030.0), "another instance does not know it"
    assert not tokens.verify("m1abc." + "A" * 43, instance="m1abc", now=1030.0), "a guessed secret is refused"
    assert not tokens.verify(tok, instance="m1abc", now=1061.0), "expired"
    assert tokens.prefix("no-dot") == "" and tokens.prefix("bad\r\nhdr.x") == ""


def test_no_instance_no_token(monkeypatch):
    from nucleo.daemon_egress import tokens
    monkeypatch.delenv("FLY_MACHINE_ID", raising=False)
    assert tokens.instance_id() is None and tokens.mint() is None, "a self-hosted engine offers no tunnel"


# ── two streams over one socket ───────────────────────────────────────────────────────────────────────────────

def test_one_session_multiplexes_two_streams_without_mixing_them():
    import base64
    import json

    from nucleo.daemon_egress.mux import Session

    async def scenario():
        to_daemon: asyncio.Queue = asyncio.Queue()
        to_engine: asyncio.Queue = asyncio.Queue()

        async def daemon():
            while True:
                f = json.loads(await to_daemon.get())
                if f["t"] == "open":
                    await to_engine.put(json.dumps({"t": "ok", "id": f["id"]}))
                elif f["t"] == "data":
                    body = base64.b64decode(f["b64"])
                    reply = f"{f['id']}:".encode() + body.upper()
                    await to_engine.put(json.dumps({"t": "data", "id": f["id"],
                                                    "b64": base64.b64encode(reply).decode()}))

        s = Session(to_daemon.put, to_engine.get)
        runner = asyncio.create_task(s.run())
        d = asyncio.create_task(daemon())
        a, b = await asyncio.gather(s.open("a.example.com", 443), s.open("b.example.org", 443))
        await a.write(b"alpha")
        await b.write(b"bravo")
        await b.write(b"bis")
        ra, rb1, rb2 = await a.read(), await b.read(), await b.read()
        assert ra == f"{a.id}:ALPHA".encode() and rb1 == f"{b.id}:BRAVO".encode() and rb2 == f"{b.id}:BIS".encode()
        assert s.hosts_last_hour() == 2
        await to_engine.put(json.dumps({"t": "close", "id": a.id}))
        assert await a.read() == b""
        await s.close()
        runner.cancel()
        d.cancel()
    asyncio.run(asyncio.wait_for(scenario(), 10))   # a stream read that never comes fails, never hangs


# ── end to end ─────────────────────────────────────────────────────────────────────────────────────────────────

class _Echo:
    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen()
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._one, args=(c,), daemon=True).start()

    @staticmethod
    def _one(c):
        try:
            while data := c.recv(65536):
                c.sendall(b"echo:" + data)
        except OSError:
            pass
        c.close()


@pytest.fixture
def ws_root(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from daemon import config as dcfg
    dcfg.reset_cache()
    yield tmp_path
    dcfg.reset_cache()


def test_offer_dial_and_one_connect_round_trip(ws_root, monkeypatch):
    import uvicorn
    from fastapi import FastAPI

    from daemon import config as dcfg
    from daemon.egress import tunnel as tmod
    from daemon.relay import dispatch
    from nucleo.daemon_egress import link
    from server import daemon_tunnel

    monkeypatch.setenv("FLY_MACHINE_ID", "m1abc")
    link.reset_for_tests()
    dcfg.save_egress(True, consent=True)

    echo = _Echo()
    asked: list = []

    def opener(host, port):
        asked.append((host, port))
        return socket.create_connection(("127.0.0.1", echo.port)), host

    daemon_tunnel_ = tmod.Tunnel(opener=opener, relay_url="http://127.0.0.1:1")
    monkeypatch.setattr(tmod, "TUNNEL", daemon_tunnel_)

    app = FastAPI()
    app.include_router(daemon_tunnel.router)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", lifespan="off"))
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    asyncio.run_coroutine_threadsafe(server.serve(), loop)
    try:
        assert _wait(lambda: server.started)
        port = server.servers[0].sockets[0].getsockname()[1]
        monkeypatch.setenv("ZAELAR_TUNNEL_ORIGIN", f"http://127.0.0.1:{port}")

        commands: list = []

        class FakeRelay:
            @staticmethod
            def hosted():
                return True

            @staticmethod
            async def command(op, args=None, *, deadline_ms=30_000):
                commands.append(op)
                frame = {"t": "command", "id": "c1", "op": op, "args": args or {}, "deadline_ms": deadline_ms}
                return await asyncio.to_thread(dispatch.handle, frame)

        monkeypatch.setattr(link, "_relay_link", lambda: FakeRelay)
        presence = {"connected": True, "caps": ["files.list", "egress"], "version": "0.2.3"}
        assert link.status(presence) == {"capable": True, "enabled": True, "connected": False, "hosts_last_hour": 0}
        assert link.launch_args() == [], "no tunnel yet: the launch is what it always was"

        asyncio.run_coroutine_threadsafe(link.tick(presence), loop).result(10)
        assert commands == ["egress.offer"]
        assert _wait(link.connected), daemon_tunnel_.status
        args = link.launch_args()
        assert args and args[0].startswith("--proxy-server=http://127.0.0.1:"), args

        proxy_port = int(link.proxy_url().rsplit(":", 1)[1])
        c = socket.create_connection(("127.0.0.1", proxy_port), timeout=5)
        c.sendall(b"CONNECT www.example.com:443 HTTP/1.1\r\nHost: www.example.com:443\r\n\r\n")
        head = b""
        while b"\r\n\r\n" not in head:
            head += c.recv(1024)
        assert head.startswith(b"HTTP/1.1 200"), head
        c.sendall(b"ping")
        got = b""
        while len(got) < len(b"echo:ping"):
            got += c.recv(1024)
        assert got == b"echo:ping"
        assert asked == [("www.example.com", 443)], "the daemon was asked for the host, the engine never resolved it"
        assert link.status(presence)["hosts_last_hour"] == 1
        c.close()

        # a renewal while carrying is NOT re-offered until half the token's life is gone
        asyncio.run_coroutine_threadsafe(link.tick(presence), loop).result(10)
        assert commands == ["egress.offer"]
        # he switched it off: `egress` leaves his capabilities and the engine closes the tunnel
        asyncio.run_coroutine_threadsafe(link.tick({"connected": True, "caps": ["files.list"]}), loop).result(10)
        assert _wait(lambda: not link.connected()) and link.launch_args() == []
    finally:
        daemon_tunnel_.stop()
        asyncio.run_coroutine_threadsafe(link.stop(), loop).result(10)
        server.should_exit = True
        _wait(lambda: not server.started, 5)
        loop.call_soon_threadsafe(loop.stop)
        link.reset_for_tests()
        echo.sock.close()
