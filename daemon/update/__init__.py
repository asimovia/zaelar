"""The daemon's SIGNED AUTO-UPDATE (V2-869 §4).

    manifest   the shape of `update-manifest.json`, shared by the CI writer and this client
    minisign   reads `.minisig` signatures; `ed25519` verifies them (pure Python: the daemon stays stdlib-only)
    state      `<state dir>/update/state.json` and the idle → downloading → ready / failed machine
    check      find the newest release that carries a manifest, VERIFY it, compare versions (daily + on demand)
    apply      download the platform's asset, verify sha256 (and cosign when present), swap, relaunch

THE ONE RULE: ANY VERIFICATION FAILURE LEAVES THE INSTALLED DAEMON UNTOUCHED. An unsigned manifest, a signature by
an unknown key, a manifest naming another release, a size or sha256 that does not match, a bundle whose code
signature does not verify — each ends in `state = failed` with the reason, and the program on disk is the one that
was there before. The swap happens only from `ready`, and `ready` is only reachable through `downloading` after the
manifest verified (see `state.py`).

WHAT VOUCHES FOR WHAT. The manifest's minisign signature is made in CI with a key that is never in the release; the
client verifies it against `PUBLIC_KEY`, committed here (so trusting this repository's `main` is the only trust
decision). The manifest pins each asset's sha256 and size, so a verified manifest transitively pins the bytes. The
Sigstore bundle over `SHA256SUMS-*` (checked when `cosign` is on PATH) and, on macOS, the bundle's own code
signature are additional, independent checks — never substitutes.

`/health` carries `update = {current, available, state, error, last_check}` through `health_fields()`; nothing in
it is fetched while answering — it reads the persisted state.
"""
from __future__ import annotations

import os
from pathlib import Path

from .. import VERSION

_HERE = Path(__file__).resolve().parent

#: The minisign PUBLIC key manifests must be signed with. Committed on purpose: it is public by definition, and the
#: client must never fetch the key it verifies with from the same place as the thing it verifies.
PUBLIC_KEY_FILE = _HERE / "PUBLIC_KEY"

#: The oldest engine build this daemon works with, published in the manifest so the engine can say "your daemon is
#: newer than this engine understands". 0 = any engine. Raise it the day a daemon needs an engine route older engines
#: lack.
MIN_ENGINE_BUILD = 0

# `build.py` stamps the engine's `update/BUILD` into the packaged daemon as `daemon/update/BUILD`; a source tree reads
# the engine's file directly. The same integer the engine shows, so "your daemon is older" is one comparison.
_STAMPED_BUILD = _HERE / "BUILD"
_ENGINE_BUILD = _HERE.parent.parent / "update" / "BUILD"


def _read_build(path: Path) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip() or 0)
    except Exception:   # noqa: BLE001 — absent or unreadable is "unknown", which is 0
        return 0


DEFAULT_REPO = "asimovia/zaelar"


def repo() -> str:
    """The repository whose releases are checked. A fork that publishes its own releases sets ZAELAR_DAEMON_REPO
    (and ships its own `PUBLIC_KEY`) — the same override `get.sh` honours."""
    return (os.getenv("ZAELAR_DAEMON_REPO") or "").strip() or DEFAULT_REPO


def current_build() -> int:
    return _read_build(_STAMPED_BUILD) or _read_build(_ENGINE_BUILD)


def current() -> dict:
    return {"version": VERSION, "build": current_build()}


def public_keys(learned: str | None = None) -> list:
    """The committed key, plus a `next_key` learned from a verified manifest (rotation)."""
    from . import minisign   # noqa: PLC0415
    keys = []
    try:
        keys.append(minisign.parse_public_key(PUBLIC_KEY_FILE.read_text(encoding="utf-8")))
    except Exception:   # noqa: BLE001 — a build without its key verifies nothing, which refuses everything
        pass
    if learned:
        try:
            keys.append(minisign.parse_public_key(learned))
        except Exception:   # noqa: BLE001
            pass
    return keys


def enabled() -> bool:
    """The background check runs only for an INSTALLED daemon (a source tree updates with git) and can be turned off
    with `ZAELAR_DAEMON_AUTO_UPDATE=0`. The on-demand check from the tray always works."""
    if (os.getenv("ZAELAR_DAEMON_AUTO_UPDATE") or "").strip() == "0":
        return False
    from . import apply   # noqa: PLC0415
    return apply.installed_target() is not None


def health_fields() -> dict:
    """`{"update": {...}}`, ready to `**`-merge into `/health`. Reads persisted state only — no network, no disk walk
    beyond one small JSON file — and starts the daily background check the first time it is asked, if enabled."""
    from . import check   # noqa: PLC0415
    from .state import STORE   # noqa: PLC0415
    try:
        check.ensure_started()
    except Exception:   # noqa: BLE001 — /health must answer even if the scheduler cannot start
        pass
    snap = STORE.snapshot()
    return {"update": {
        "current": current(),
        "available": snap.get("available"),
        "state": snap.get("state", "idle"),
        "error": snap.get("error", ""),
        "last_check": snap.get("last_check", 0),
    }}


__all__ = ["PUBLIC_KEY_FILE", "MIN_ENGINE_BUILD", "current", "current_build", "health_fields", "public_keys",
           "enabled", "repo"]
