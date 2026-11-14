"""A tiny durable JSON document (atomic replace, 0600). The a2a package keeps its state in files, not the DB, so that
it survives restarts without a migration and stays independent of the engine's stores."""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path


def default_state_dir() -> Path:
    """`A2A_STATE_DIR` > `<workspace>/.meshkore/credentials/a2a` (private, already ignored by git)."""
    env = os.getenv("A2A_STATE_DIR")
    if env:
        return Path(env)
    try:
        from nucleo import workspace
        root = workspace.root()
    except Exception:
        root = Path(__file__).resolve().parents[1]
    return root / ".meshkore" / "credentials" / "a2a"


class JsonDoc:
    def __init__(self, path: Path, default: dict):
        self.path = Path(path)
        self._default = default
        self._lock = threading.RLock()
        self.data = self._load()

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except (FileNotFoundError, ValueError):
            return json.loads(json.dumps(self._default))

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".a2a-", suffix=".json")
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=1, sort_keys=True)
                os.chmod(tmp, 0o600)
                os.replace(tmp, self.path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except FileNotFoundError:
                    pass
                raise
