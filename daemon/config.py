"""`daemon.json` — the daemon's only persistent state: the port, the API token, the folder allowlist, and which
browser its windows open in (`browser`).

Written atomically (tmp + `os.replace`), which is the house pattern (`config/connectors.py`, `config/v2.py`,
`config/credentials.py`) and matters more here than usual: the allowlist IS the permission circuit, and a
half-written allowlist after a crash would either lock the user out of their own folders or — the direction that
actually costs something — leave a truncated JSON that the loader falls back on with defaults, silently widening
or narrowing what the agent can reach without anybody being told.

The file is created 0600. It holds the API token, so it is a credential file even though it is not in
`credentials/`: anything that can read it can read every folder the user granted.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
from pathlib import Path

from . import PORT
from .paths import config_file

_LOCK = threading.Lock()

# Read once, then served from memory. The HTTP handler is threaded, and re-reading the file per request would
# make the allowlist check depend on filesystem timing — the last thing a permission check should depend on.
_CACHE: dict | None = None


def _defaults() -> dict:
    return {
        "version": 1,
        "port": PORT,
        # 32 bytes of urandom, hex. Required on every route but /health (see `server.py`): loopback alone is not
        # a boundary — every other process on the machine, and any web page the user has open, can reach
        # 127.0.0.1 too.
        "token": secrets.token_hex(32),
        # EMPTY UNTIL THE USER CHOOSES, and this is the load-bearing line of the whole permission circuit.
        #
        # The decision is "Documents by default", and the obvious reading — seed `roots` with `~/Documents` on
        # first run — was what this originally did. It is wrong: installing the daemon would then make every
        # document on the machine readable by the agent BEFORE the user had been shown a single screen, which is
        # a permission nobody granted. "By default" is about what the wizard PROPOSES (Documents is the one
        # entry pre-checked, see `permissions.candidates()`), not about what is readable before it has run.
        #
        # So a fresh install can read nothing at all, and `configured` below is how the engine tells "the user
        # has not chosen yet" (show the wizard) from "the user chose nothing" (respect it).
        "roots": [],
        "configured": False,
        # Which browser the daemon's windows open in. `channel` is the last one MEASURED usable ("chrome" — the
        # person's own Google Chrome program — or "chromium", the one the daemon downloaded); "" means none yet.
        # A record, not an instruction: the browser is re-measured on every launch (`daemon.browser.channel`).
        # `auto_download`: may the resident fetch a Chromium on first run when there is no Chrome. Cancelling the
        # download turns it off, so a person who said no is not asked again by the next start.
        "browser": {"channel": "", "auto_download": True},
    }


_KEYS = ("port", "token", "roots", "configured", "browser")


def _clean_browser(raw) -> dict:
    """Only the two known fields, each in its own domain. A hand-edited file cannot smuggle a path or a flag in."""
    out = {"channel": "", "auto_download": True}
    if isinstance(raw, dict):
        if raw.get("channel") in ("", "chrome", "chromium"):
            out["channel"] = raw["channel"]
        if isinstance(raw.get("auto_download"), bool):
            out["auto_download"] = raw["auto_download"]
    return out


def load() -> dict:
    """The current config, creating the file with defaults on first run. Never raises: a daemon that cannot read
    its own config still answers /health, and /health is how the user finds out."""
    global _CACHE
    with _LOCK:
        if _CACHE is not None:
            return dict(_CACHE)
        path = config_file()
        data: dict = {}
        try:
            data = json.loads(path.read_text(encoding="utf-8")) or {}
        except FileNotFoundError:
            data = {}
        except Exception:       # noqa: BLE001 — corrupt file: fall back to defaults rather than refusing to run
            data = {}
        merged = _defaults()
        # Only take keys we know. A stray key from a newer version must not become an allowlist entry.
        for key in _KEYS:
            if key in data:
                merged[key] = data[key]
        merged["browser"] = _clean_browser(merged.get("browser"))
        if not isinstance(merged.get("roots"), list):
            merged["roots"] = []
        merged["roots"] = [str(r) for r in merged["roots"] if isinstance(r, str) and r.strip()]
        # A SHORT token is worse than a missing one: it looks configured and is guessable. A file edited by
        # hand, or truncated by a crash, is exactly how one appears — so the length is enforced on the way in
        # rather than trusted from disk.
        if not isinstance(merged.get("token"), str) or len(merged["token"]) < 32:
            merged["token"] = secrets.token_hex(32)
        # The port decides what `is_running` probes and what the Host guard compares against. A string, a float
        # or something outside the legal range would make both of those quietly wrong.
        try:
            port = int(merged.get("port") or PORT)
        except (TypeError, ValueError):
            port = PORT
        merged["port"] = port if 1 <= port <= 65535 else PORT
        _CACHE = merged
        if not path.exists():
            _write(merged)
        return dict(merged)


def save(patch: dict) -> dict:
    """Merge `patch` into the config and persist it. Returns the new config."""
    global _CACHE
    load()                      # make sure the cache is warm before mutating it
    with _LOCK:
        assert _CACHE is not None
        _CACHE.update({k: v for k, v in patch.items() if k in _KEYS})
        _CACHE["browser"] = _clean_browser(_CACHE.get("browser"))
        _write(_CACHE)
        return dict(_CACHE)


def _write(data: dict) -> None:
    path = config_file()
    tmp = Path(str(path) + ".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        # 0600 BEFORE the rename, so the file is never briefly world-readable under its real name. No-op on
        # Windows, where the ACL inherited from LOCALAPPDATA is already per-user.
        try:
            os.chmod(tmp, 0o600)
        except Exception:       # noqa: BLE001
            pass
        os.replace(tmp, path)
    except Exception:           # noqa: BLE001 — see the module docstring: persisting must not stop serving
        try:
            tmp.unlink()
        except Exception:       # noqa: BLE001
            pass


def browser() -> dict:
    """The `browser` section, always complete."""
    return dict(load().get("browser") or {})


def save_browser(**fields) -> dict:
    """Merge into the `browser` section and persist. Unknown fields and values outside their domain are dropped."""
    merged = {**browser(), **fields}
    return dict(save({"browser": _clean_browser(merged)}).get("browser") or {})


def token() -> str:
    return str(load().get("token") or "")


def rotate_token() -> str:
    """Mint a new API token and persist it. Returns the new one.

    A credential with no way to replace it is a credential you cannot respond to. If this one is ever printed
    into a shared terminal, pasted into a bug report or read by something that should not have it, the answer
    has to be one command rather than "delete the config and reconfigure your folders" — which is the workaround
    people find on their own, and it throws away the allowlist along with the secret.

    The running daemon keeps the OLD token in memory until it restarts, deliberately: rotating out from under a
    live process would break the engine mid-request with no way to tell it why."""
    fresh = secrets.token_hex(32)
    save({"token": fresh})
    return fresh


def reset_cache() -> None:
    """Drop the in-memory copy. For tests only — the daemon itself never needs it, and a caller that reaches for
    it in production is asking the permission check to re-read the disk mid-flight."""
    global _CACHE
    with _LOCK:
        _CACHE = None
