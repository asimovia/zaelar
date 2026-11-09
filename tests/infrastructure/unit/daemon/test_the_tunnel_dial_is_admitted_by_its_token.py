"""His daemon's tunnel dial reaches the instance that offered it — by the token's prefix, with no session cookie —
and only that instance's own token set lets it in (V2-836).

On a shared hostname a WebSocket never passes the HTTP admission middleware (ASGI scope `websocket`), so
`server/ingress.py` has a WebSocket gate of its own: an allowlist (`/daemon/tunnel` only), a `307 fly-replay:
instance=<prefix>` when the token names another instance, the route itself when it names this one. The route then
checks the token against what THIS instance minted and closes 4401 on anything else — a wrong prefix, a guessed
secret, an expired token.

Driven through Starlette's TestClient over the real `ingress.install` + the real route.
Disarms (seen red 2026-11-09): `decide_websocket` admitting any path → the allowlist case red; the replay sent
without the prefix comparison (always SERVE) → the replay case red; the route accepting without `tokens.verify` →
the 4401 cases red.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("FLY_MACHINE_ID", "m1abc")
    monkeypatch.setenv("ZAELAR_ACCOUNT_ROUTER", "1")
    from nucleo.daemon_egress import link, tokens
    from server import daemon_tunnel, ingress
    link.reset_for_tests()
    tokens.forget_all()
    a = FastAPI()
    ingress.install(a)
    a.include_router(daemon_tunnel.router)

    @a.websocket("/other/socket")
    async def other(ws):
        await ws.accept()
        await ws.close()
    yield a
    link.reset_for_tests()


def test_the_pure_decision():
    from server import ingress
    d = ingress.decide_websocket
    assert d(path="/daemon/tunnel", bearer="m1abc.secret", mine="m1abc")[0] == ingress.SERVE
    assert d(path="/daemon/tunnel", bearer="m2zzz.secret", mine="m1abc") == (ingress.REPLAY,
                                                                               "token_names_another_instance", "m2zzz")
    assert d(path="/daemon/tunnel", bearer="", mine="m1abc")[0] == ingress.DENY
    assert d(path="/daemon/tunnel", bearer="evil\r\nx.y", mine="m1abc")[0] == ingress.DENY, "no header injection"
    assert d(path="/other/socket", bearer="m1abc.secret", mine="m1abc")[0] == ingress.DENY
    assert "/daemon/tunnel" not in ingress.PUBLIC_EXACT, "admitted by its token, not as a public path"


def test_a_token_of_another_instance_is_replayed_there_without_a_cookie(app):
    with TestClient(app) as client:
        with pytest.raises(Exception) as e:
            with client.websocket_connect("/daemon/tunnel", headers={"Authorization": "Bearer m2zzz.whatever"}):
                pass
    resp = e.value
    assert getattr(resp, "status_code", None) == 307, repr(resp)
    assert resp.headers.get("fly-replay") == "instance=m2zzz"


def test_a_websocket_off_the_allowlist_is_refused(app):
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/other/socket") as ws:
                ws.receive_text()


def _closed_with(app, token):
    with TestClient(app) as client:
        with client.websocket_connect("/daemon/tunnel", headers={"Authorization": f"Bearer {token}"}) as ws:
            with pytest.raises(WebSocketDisconnect) as e:
                ws.receive_text()
    return e.value.code


def test_this_instance_closes_4401_on_a_token_it_did_not_mint(app):
    assert _closed_with(app, "m1abc." + "A" * 43) == 4401


def test_an_expired_token_is_closed_4401(app):
    from nucleo.daemon_egress import tokens
    tok, _ = tokens.mint(instance="m1abc", ttl=-1)
    assert _closed_with(app, tok) == 4401


def test_a_fresh_token_of_this_instance_is_let_in(app, monkeypatch):
    from nucleo.daemon_egress import link, tokens
    seen = {}

    async def attach(send, recv, close):
        seen["in"] = True
        await close()
    monkeypatch.setattr(link, "attach", attach)
    tok, _ = tokens.mint(instance="m1abc")
    code = _closed_with(app, tok)
    assert seen.get("in") and code == 1000


def test_a_self_hosted_engine_has_no_gate_and_no_tunnel(monkeypatch):
    """Not a routing process: the gate is a pass-through, and with no instance id no token verifies."""
    monkeypatch.delenv("FLY_MACHINE_ID", raising=False)
    monkeypatch.delenv("ZAELAR_ACCOUNT_ROUTER", raising=False)
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    from server import daemon_tunnel, ingress
    a = FastAPI()
    ingress.install(a)
    a.include_router(daemon_tunnel.router)
    assert _closed_with(a, "m1abc." + "A" * 43) == 4401
