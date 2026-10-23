"""Spotify's return address is derived from the origin the browser is on, and the exchange presents the same one.

It was a fixed loopback address: on an engine reached through its own domain, Spotify sent the code back to the
visitor's computer, where nothing listens.
"""
from __future__ import annotations

import urllib.parse


class _Resp:
    status_code = 200

    def json(self):
        return {"access_token": "at", "refresh_token": "rt", "expires_in": 3600}


def test_the_login_returns_to_the_origin_it_started_from(monkeypatch, tmp_path):
    import httpx
    from connectors.spotify import auth
    monkeypatch.setattr(auth, "STORE", tmp_path / "spotify.json")
    monkeypatch.delenv("SPOTIFY_REDIRECT_URI", raising=False)
    sent = {}
    monkeypatch.setattr(httpx, "post", lambda url, data=None, timeout=None: sent.update(data) or _Resp())
    r = auth.begin_login("https://agent.example.test")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(r["url"]).query)
    assert q["redirect_uri"] == ["https://agent.example.test/api/spotify/callback"]
    assert auth.complete_login("c", q["state"][0])["ok"]
    assert sent["redirect_uri"] == "https://agent.example.test/api/spotify/callback"


def test_a_local_browser_still_returns_to_loopback(monkeypatch):
    from connectors.spotify import auth
    monkeypatch.delenv("SPOTIFY_REDIRECT_URI", raising=False)
    assert auth.redirect_uri("") == auth._DEFAULT_REDIRECT
    assert auth.redirect_uri("http://localhost:43917").startswith("http://127.0.0.1:")
    assert auth.redirect_uri("javascript:alert(1)") == auth._DEFAULT_REDIRECT
