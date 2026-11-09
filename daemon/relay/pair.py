"""Pairing: a one-time code shown by his agent becomes this daemon's relay credential.

    POST <relay>/daemon/pair {"code": "ABCD-EFGH", "device": {"platform", "version", "hostname_hash"}}
      → {"credential": "<opaque>", "account_hint": "…", "relay_url": "https://…"}

No authentication on the request: the code IS the proof (one use, short-lived, rate-limited by the relay). The
credential lands in `relay.json` (0600) and the link starts. The device's hostname is sent HASHED — enough for him to
tell two of his computers apart in a list, nothing a reader of that list learns his machine's name from.

Two doors, one function: `python -m daemon.relay pair <CODE>` from a terminal, and `pair_and_connect(code)` in process
for the tray.
"""
from __future__ import annotations

import hashlib
import json
import re
import socket
import urllib.error
import urllib.request

from .. import VERSION, audit
from . import config

_CODE_RE = re.compile(r"^[A-Z0-9]{4}-?[A-Z0-9]{4}$")
_TIMEOUT_S = 15.0


class PairingError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def normalize_code(raw: str) -> str:
    code = re.sub(r"\s+", "", (raw or "")).upper()
    if not _CODE_RE.match(code):
        raise PairingError("bad_code", "A pairing code looks like ABCD-EFGH.")
    return code if "-" in code else f"{code[:4]}-{code[4:]}"


def device() -> dict:
    from .client import platform_name
    try:
        host = socket.gethostname()
    except OSError:
        host = ""
    return {"platform": platform_name(), "version": VERSION,
            "hostname_hash": hashlib.sha256(host.encode("utf-8")).hexdigest()[:16]}


def _post(url: str, body: dict) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": f"zaelar-daemon/{VERSION}"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as r:     # noqa: S310 — the URL passed `acceptable()`
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read() or b""
    try:
        data = json.loads(raw or b"{}")
    except ValueError:
        data = {}
    return status, data if isinstance(data, dict) else {}


#: The one HTTP seam (replaced by tests).
POST = _post


def pair(code: str, relay_url: str = "") -> dict:
    """Redeem `code` at the relay and store the credential. Returns `{account_hint, relay_url}`; raises
    `PairingError` with a code the caller can branch on (`bad_code` · `no_relay` · `rejected` · `unreachable`)."""
    code = normalize_code(code)
    base = (relay_url or config.url()).rstrip("/")
    if not base or not config.acceptable(base):
        raise PairingError("no_relay", "This daemon has no relay address to pair with.")
    try:
        status, data = POST(config.http_url(base, "/daemon/pair"), {"code": code, "device": device()})
    except Exception as e:  # noqa: BLE001
        raise PairingError("unreachable", f"The relay could not be reached ({type(e).__name__}).") from None
    credential = data.get("credential") if isinstance(data.get("credential"), str) else ""
    if status != 200 or len(credential) < 32:
        audit.record("relay.pair", caller="relay", outcome="refused", reason=f"http_{status}")
        raise PairingError("rejected", "The relay did not accept that code (wrong, used or expired).")
    hint = str(data.get("account_hint") or "")[:120]
    stored_url = str(data.get("relay_url") or "") or base
    config.store_pairing(credential, relay_url=stored_url if config.acceptable(stored_url) else base, account_hint=hint)
    audit.record("relay.pair", caller="relay", outcome="ok")
    return {"account_hint": hint, "relay_url": config.url()}


def pair_and_connect(code: str, relay_url: str = "") -> dict:
    """The tray's door: pair, then (re)start the link with the new credential."""
    out = pair(code, relay_url)
    from . import client
    client.CLIENT.stop("re-pair")
    client.CLIENT.join(5)
    out["connecting"] = client.CLIENT.start()
    return out


def unpair() -> None:
    from . import client
    client.CLIENT.stop("unpair")
    config.forget()
    audit.record("relay.unpair", caller="local", outcome="ok")
