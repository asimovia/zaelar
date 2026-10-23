"""A refresh the provider answers with `invalid_grant` disconnects the account (connectors/oauth_base.py).

The grant is gone for good, so the dead tokens are dropped and the card offers to connect again, instead of saying
«connected» while every call fails. Any other refresh failure keeps the account as it is.
"""
from __future__ import annotations

import pytest


class _Resp:
    def __init__(self, payload):
        self._p, self.status_code = payload, 400
        self.text = str(payload)

    def json(self):
        return self._p


@pytest.fixture
def calendar(monkeypatch):
    from connectors.calendar import oauth
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "own.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "own-secret")
    oauth._store_tokens("google", "", {"access_token": "at", "refresh_token": "rt", "expires_in": 3600})
    data = oauth._load()
    data["accounts"]["google"]["expires_at"] = 0          # expired: the next read must refresh
    oauth._save(data)
    yield oauth
    oauth._b.forget(oauth._m, "google")


def _answer(monkeypatch, payload):
    import httpx
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp(payload))


def test_a_revoked_grant_disconnects(calendar, monkeypatch):
    _answer(monkeypatch, {"error": "invalid_grant", "error_description": "Token has been expired or revoked."})
    assert calendar.access_token("google") is None
    assert not calendar.tokens_present("google")
    assert not next(s for s in calendar.status() if s["id"] == "google")["connected"]


def test_another_refresh_failure_keeps_the_account(calendar, monkeypatch):
    _answer(monkeypatch, {"error": "temporarily_unavailable"})
    assert calendar.access_token("google") == "at"
    assert calendar.tokens_present("google")


def test_a_revoked_spotify_grant_disconnects(monkeypatch):
    from connectors.spotify import auth
    auth._save({"tokens": {"access_token": "at", "refresh_token": "rt", "expires_at": 0}})
    _answer(monkeypatch, {"error": "invalid_grant", "error_description": "Refresh token revoked"})
    try:
        assert auth.access_token() == ""
        assert not auth.logged_in()
    finally:
        auth.disconnect()


def test_another_spotify_refresh_failure_keeps_the_session(monkeypatch):
    from connectors.spotify import auth
    auth._save({"tokens": {"access_token": "at", "refresh_token": "rt", "expires_at": 0}})
    _answer(monkeypatch, {"error": "server_error"})
    try:
        auth.access_token()
        assert auth.logged_in()
    finally:
        auth.disconnect()
