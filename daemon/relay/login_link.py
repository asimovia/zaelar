"""A one-time sign-in link for «Open Zaelar» from the daemon (OPTIONAL relay endpoint).

    GET <relay>/daemon/login-link   Authorization: Bearer <credential>
      → 200 {"url": "https://…", "expires_at": "<iso>"}      404 when the relay does not offer it

A paired daemon already proves it belongs to an account, so it can ask the relay for a short-lived link that opens his
agent signed in, instead of making him type a password on the computer he just paired. The relay may not offer this
endpoint: `login_link()` then returns None and the caller opens the plain address.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from .. import VERSION
from . import config

_TIMEOUT_S = 10.0


def _get(url: str, credential: str) -> tuple[int, dict]:
    req = urllib.request.Request(url, method="GET", headers={"Authorization": f"Bearer {credential}",
                                                             "User-Agent": f"zaelar-daemon/{VERSION}"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as r:     # noqa: S310 — the URL passed `acceptable()`
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, b""
    try:
        data = json.loads(raw or b"{}")
    except ValueError:
        data = {}
    return status, data if isinstance(data, dict) else {}


#: The one HTTP seam (replaced by tests).
GET = _get


def login_link() -> dict | None:
    """`{url, expires_at}` or None (not paired, relay without the endpoint, unreachable, or a non-https link)."""
    cfg = config.load()
    if not (cfg.get("url") and cfg.get("credential")):
        return None
    try:
        status, data = GET(config.http_url(cfg["url"], "/daemon/login-link"), cfg["credential"])
    except Exception:   # noqa: BLE001 — optional: fall back to the plain address
        return None
    link = str(data.get("url") or "")
    if status != 200 or not link.startswith("https://"):
        return None
    return {"url": link, "expires_at": str(data.get("expires_at") or "")}
