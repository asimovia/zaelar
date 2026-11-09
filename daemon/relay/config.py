"""`relay.json` — where the relay is and the credential this daemon presents to it.

A SEPARATE FILE from `daemon.json` on purpose: that one is the loopback surface (port, API token, folder allowlist) and
this one is the outbound link. Forgetting the relay credential (a `bye revoked`, an «unpair») must never touch the
allowlist, and a corrupt relay file must never cost the user their folders.

    {"url": "https://relay.example", "credential": "<opaque>", "paired_at": 1731100000, "account_hint": "a…@…"}

WHERE THE URL COMES FROM, in order: `ZAELAR_DAEMON_RELAY_URL` (a power user or a test), the file (what pairing stored),
then a `build_defaults.json` next to the program (`{"relay_url": …}`, left there by whoever packaged it). No URL means
no relay: loopback only, exactly the P0-P2 daemon. The URL is not a secret; the credential is, so the file is 0600
and written atomically like `daemon.json`.

THE CREDENTIAL TRAVELS ONLY ENCRYPTED. `url()` refuses a plain-http relay unless it is on this machine (a test's fake
relay): a bearer credential sent over cleartext to the network is a credential given away.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from .. import paths

ENV_URL = "ZAELAR_DAEMON_RELAY_URL"
_KEYS = ("url", "credential", "paired_at", "account_hint")
_LOCK = threading.Lock()
_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def relay_file() -> Path:
    return paths.state_dir() / "relay.json"


def _read_file() -> dict:
    try:
        data = json.loads(relay_file().read_text(encoding="utf-8"))
    except Exception:       # noqa: BLE001 — absent or corrupt: not paired
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: data[k] for k in _KEYS if k in data}


def _build_defaults_dirs() -> list[Path]:
    """Where a packaged daemon finds `build_defaults.json`: beside the program (the onefile binary or the zipapp)."""
    out: list[Path] = []
    if getattr(sys, "frozen", False):
        out.append(Path(sys.executable).resolve().parent)
    root = Path(__file__).resolve().parent.parent.parent
    if root.is_file():                       # a zipapp: the archive itself
        out.append(root.parent)
    return out


def _build_default_url() -> str:
    for d in _build_defaults_dirs():
        try:
            data = json.loads((d / "build_defaults.json").read_text(encoding="utf-8"))
        except Exception:   # noqa: BLE001 — optional file
            continue
        if isinstance(data, dict) and isinstance(data.get("relay_url"), str):
            return data["relay_url"].strip()
    return ""


def acceptable(url: str) -> bool:
    """https/wss anywhere; http/ws only to this machine. Anything else is not a relay this daemon talks to."""
    parts = urlsplit((url or "").strip())
    if not parts.hostname:
        return False
    if parts.scheme in ("https", "wss"):
        return True
    return parts.scheme in ("http", "ws") and parts.hostname in _LOOPBACK_HOSTS


def url() -> str:
    """The relay's base URL (`https://host[/prefix]`), or "" when there is none this daemon may use."""
    for candidate in ((os.getenv(ENV_URL) or "").strip(), str(_read_file().get("url") or "").strip(),
                      _build_default_url()):
        if candidate:
            return candidate.rstrip("/") if acceptable(candidate) else ""
    return ""


def credential() -> str:
    raw = _read_file().get("credential")
    return raw.strip() if isinstance(raw, str) else ""


def load() -> dict:
    """The effective view: the file's fields with the resolved URL. Never raises."""
    data = _read_file()
    data["url"] = url()
    data["credential"] = credential()
    return data


def paired() -> bool:
    return bool(url() and credential())


def ws_url(base: str) -> str:
    """`https://h/p` → `wss://h/p/daemon/relay` (and http → ws for a loopback test relay)."""
    parts = urlsplit(base)
    scheme = {"https": "wss", "http": "ws"}.get(parts.scheme, parts.scheme)
    return f"{scheme}://{parts.netloc}{parts.path.rstrip('/')}/daemon/relay"


def http_url(base: str, path: str) -> str:
    parts = urlsplit(base)
    scheme = {"wss": "https", "ws": "http"}.get(parts.scheme, parts.scheme)
    return f"{scheme}://{parts.netloc}{parts.path.rstrip('/')}{path}"


def save(patch: dict) -> dict:
    """Merge `patch` (known keys only) into the file and persist it 0600. Returns the file's new content."""
    with _LOCK:
        data = _read_file()
        data.update({k: v for k, v in patch.items() if k in _KEYS})
        data = {k: v for k, v in data.items() if v not in (None, "")}
        _write(data)
        return dict(data)


def store_pairing(credential: str, *, relay_url: str = "", account_hint: str = "") -> dict:
    patch: dict = {"credential": credential, "paired_at": int(time.time()), "account_hint": account_hint}
    if relay_url and acceptable(relay_url):
        patch["url"] = relay_url.rstrip("/")
    return save(patch)


def forget() -> None:
    """Drop the credential (and its hint), keep the URL: the next pairing goes to the same relay."""
    with _LOCK:
        data = {k: v for k, v in _read_file().items() if k == "url"}
        _write(data)


def _write(data: dict) -> None:
    path = relay_file()
    tmp = Path(str(path) + ".tmp")
    try:
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, indent=1, ensure_ascii=False))
        try:
            os.chmod(tmp, 0o600)
        except Exception:   # noqa: BLE001 — Windows: the per-user ACL already applies
            pass
        os.replace(tmp, path)
    except Exception:       # noqa: BLE001 — persisting must never take the daemon down
        try:
            tmp.unlink()
        except Exception:   # noqa: BLE001
            pass
