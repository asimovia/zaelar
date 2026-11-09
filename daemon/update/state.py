"""What the updater knows, persisted in `<daemon state dir>/update/state.json` — never in `daemon.json`.

    state        idle | downloading | ready | failed
    error        the sentence that explains `failed` (empty otherwise)
    last_check   epoch seconds of the last completed check (successful or not)
    last_result  one line: "up to date", "0.2.3 (build 124) available", the refusal…
    available    {version, build, tag, published_at} of a verified newer release, or null
    pending      {path, sha256, size, platform, version, build, tag} of a downloaded, VERIFIED artifact, or null
    next_key     a public key learned from a verified manifest (key rotation), or null

THE TRANSITIONS ARE THE MECHANISM, not documentation. `ready` can only be reached from `downloading`, and
`downloading` is only entered after a manifest verified — so "ready" always means "these exact bytes passed every
check". A transition the table does not list raises instead of quietly writing an impossible state.

    idle ──check finds newer──▶ downloading ──sha256 + size ok──▶ ready ──swapped──▶ idle (new program)
      ▲                              │                              │
      └───── next check ◀── failed ◀─┴── any verification failure ──┘

`failed` never touches the installed program: every failure path ends here with the install exactly as it was.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

ALLOWED: dict[str, set[str]] = {
    "idle": {"idle", "downloading", "failed"},
    "downloading": {"ready", "failed"},
    "ready": {"idle", "downloading", "failed"},
    "failed": {"idle", "downloading", "failed"},
}
#: Every state the machine can be in — the keys of its transitions, declared once.
STATES = tuple(ALLOWED)

_DEFAULT = {"state": "idle", "error": "", "last_check": 0, "last_result": "", "available": None,
            "pending": None, "next_key": None}


def default_dir() -> Path:
    from .. import paths   # noqa: PLC0415 — resolved at use, so a test's ZAELAR_WORKSPACE is honoured
    return paths.state_dir() / "update"


class IllegalTransition(RuntimeError):
    pass


class Store:
    """Thread-safe, lazily loaded, written atomically (temp file + `os.replace`) on every change."""

    def __init__(self, directory: Path | None = None):
        self._dir = directory
        self._lock = threading.RLock()
        self._data: dict | None = None

    @property
    def directory(self) -> Path:
        return self._dir or default_dir()

    @property
    def file(self) -> Path:
        return self.directory / "state.json"

    def staging(self) -> Path:
        d = self.directory / "staged"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _load(self) -> dict:
        if self._data is None:
            data = dict(_DEFAULT)
            try:
                raw = json.loads(self.file.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    data.update({k: raw[k] for k in _DEFAULT if k in raw})
            except Exception:   # noqa: BLE001 — no file, or a corrupt one: start from idle, never crash
                pass
            if data.get("state") not in STATES:
                data["state"] = "idle"
            # A download cannot survive a restart half-done: the process that was writing it is gone.
            if data["state"] == "downloading":
                data.update(state="failed", error="the download was interrupted")
            self._data = data
        return self._data

    def _save(self) -> None:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            tmp = self.file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(tmp, self.file)
        except Exception:   # noqa: BLE001 — an unwritable state dir degrades to in-memory, reported via /health
            pass

    def snapshot(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self._load()))

    def update(self, **fields) -> dict:
        """Change fields WITHOUT changing the state (last_check, next_key, …)."""
        if "state" in fields:
            raise IllegalTransition("use transition() to change the state")
        with self._lock:
            self._load().update(fields)
            self._save()
            return self.snapshot()

    def transition(self, new: str, **fields) -> dict:
        with self._lock:
            data = self._load()
            old = data["state"]
            if new not in STATES or new not in ALLOWED[old]:
                raise IllegalTransition(f"{old} → {new} is not a transition the updater makes")
            data.update(fields)
            data["state"] = new
            if new != "failed":
                data["error"] = ""
            self._save()
            return self.snapshot()

    def reset_cache(self) -> None:
        with self._lock:
            self._data = None


STORE = Store()
