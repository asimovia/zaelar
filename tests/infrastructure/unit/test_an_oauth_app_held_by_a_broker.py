"""An OAuth app this install does not hold is used through a broker that does (connectors/oauth_broker.py).

An instance that must not carry the app's client secret gets the client id from a broker and sends its two token
calls there; the broker adds the secret. Everything else — PKCE, `state`, the callback, the token store — stays in
the engine. And a client the install DOES hold is never routed anywhere else.
"""
from __future__ import annotations

import urllib.parse

import pytest

BROKER = "https://cp.example.test"


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def json(self):
        return self._p


@pytest.fixture
def calls(monkeypatch):
    """httpx.post recorded; the broker answers its two routes, the provider answers its token URL."""
    import httpx
    from connectors import oauth_broker
    from connectors.google import app as google_app
    seen: list[tuple[str, dict]] = []

    def post(url, json=None, data=None, headers=None, timeout=None):
        seen.append((url, dict(json or data or {}), dict(headers or {})))
        if url == BROKER + "/oauth/client":
            return _Resp({"client_id": "brokered.apps.googleusercontent.com"})
        if url == BROKER + "/oauth/token":
            return _Resp({"access_token": "at-broker", "refresh_token": "rt", "expires_in": 3600})
        return _Resp({"access_token": "at-direct", "refresh_token": "rt", "expires_in": 3600})

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(google_app, "_from_file", lambda: {})       # no console JSON on this machine
    for name in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "CALENDAR_GOOGLE_CLIENT_ID",
                 "CALENDAR_GOOGLE_CLIENT_SECRET", "ZAELAR_OAUTH_BROKER_URL"):
        monkeypatch.delenv(name, raising=False)
    oauth_broker._reset_for_tests()
    yield seen
    oauth_broker._reset_for_tests()


def _cloud(monkeypatch):
    monkeypatch.setenv("CONTROL_PLANE_URL", BROKER)
    monkeypatch.setenv("CONTROL_PLANE_SERVICE_TOKEN", "workload-token")


def _consent_and_return(origin="https://agent.example.test"):
    from connectors.calendar import oauth
    r = oauth.authorize_url("google", "", origin)
    assert r["ok"], r
    q = urllib.parse.parse_qs(urllib.parse.urlparse(r["url"]).query)
    return oauth, q, oauth.exchange_code("the-code", q["state"][0])


def test_without_a_broker_nothing_changes(calls, monkeypatch):
    monkeypatch.delenv("CONTROL_PLANE_URL", raising=False)
    monkeypatch.delenv("CONTROL_PLANE_SERVICE_TOKEN", raising=False)
    from connectors import oauth_broker
    from connectors.calendar import oauth
    assert not oauth_broker.enabled()
    assert oauth.client_id("google") == ""
    assert not oauth.authorize_url("google")["ok"], "no client anywhere: the connector stays dormant"
    assert calls == [], "no broker configured means no request to one"


def test_the_broker_supplies_the_client_and_makes_the_exchange(calls, monkeypatch):
    _cloud(monkeypatch)
    from connectors.google import app as google_app
    assert google_app.source() == "broker"
    oauth, q, res = _consent_and_return()
    assert q["client_id"] == ["brokered.apps.googleusercontent.com"]
    assert q["redirect_uri"] == ["https://agent.example.test/api/calendar/callback"]
    assert res["ok"], res
    token_calls = [c for c in calls if c[0].endswith("/token")]
    assert [c[0] for c in token_calls] == [BROKER + "/oauth/token"], "the exchange went to the broker, not Google"
    body, headers = token_calls[0][1], token_calls[0][2]
    assert body["provider"] == "google" and body["grant_type"] == "authorization_code"
    assert body["code_verifier"] and "client_secret" not in body
    assert headers.get("X-Service-Token") == "workload-token"
    assert oauth.account("google")["access_token"] == "at-broker"


def test_the_refresh_goes_to_the_broker_too(calls, monkeypatch):
    _cloud(monkeypatch)
    oauth, _q, _res = _consent_and_return()
    data = oauth._load()
    data["accounts"]["google"]["expires_at"] = 0          # expired: the next read must refresh
    oauth._save(data)
    calls.clear()
    assert oauth.access_token("google") == "at-broker"
    assert [c[0] for c in calls if c[0].endswith("/token")] == [BROKER + "/oauth/token"]
    assert calls[-1][1]["grant_type"] == "refresh_token"


def test_a_client_the_install_holds_never_leaves_for_the_broker(calls, monkeypatch):
    _cloud(monkeypatch)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "own.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "own-secret")
    _oauth, q, res = _consent_and_return()
    assert q["client_id"] == ["own.apps.googleusercontent.com"]
    assert res["ok"], res
    urls = [c[0] for c in calls]
    assert "https://oauth2.googleapis.com/token" in urls
    assert not any(u.startswith(BROKER) for u in urls), "a held client must not even ask the broker"


def test_a_provider_the_broker_does_not_serve_is_never_sent_there():
    from connectors import oauth_broker
    assert oauth_broker.family_of("https://oauth2.googleapis.com/token") == "google"
    assert oauth_broker.family_of("https://login.microsoftonline.com/common/oauth2/v2.0/token") == "microsoft"
    assert oauth_broker.family_of("https://accounts.spotify.com/api/token") == "spotify"
    assert oauth_broker.family_of("https://evil.example/token") == ""
