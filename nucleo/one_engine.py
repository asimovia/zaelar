"""One engine per machine: an OS lock the running engine holds for its whole life (2026-10-21).

Two engines on one machine cannot share what an engine owns — the voice room's worker slot, the fixed ports, the
connectors' pollers (one Telegram bot, one WhatsApp session, one mailbox). Measured: a restart freed the old
engine's port while the old process hung in its shutdown; the new one started beside it, both registered a voice
worker, and the person spoke to a room the wrong one was serving — the text reached the chat, nobody answered.

A port is not proof of life (it is the first thing a dying server lets go of), and a pid file outlives a crash. An
advisory lock is neither: the kernel releases it the instant the holder dies, `kill -9` included, so «is the lock
taken?» means exactly «is an engine alive?». It lives in the user's home, not the checkout, so a second COPY of the
repo meets the same lock instead of a port clash halfway through its boot.

Standard library only: `scripts/zaelar.py` loads this file by path to ask the same question without a venv.
"""
from __future__ import annotations

import json
import os
import sys
import time

_held = None   # the open file whose lock this process holds; closing it (or dying) releases the lock


def lock_path() -> str:
    base = os.getenv("ZAELAR_LOCK_DIR") or os.path.join(os.path.expanduser("~"), ".zaelar")
    return os.path.join(base, "engine.lock")


def _try_lock(fh) -> bool:
    """Take the lock without waiting. False means another live process holds it (the caller reads who)."""
    taken = False
    try:
        if sys.platform == "win32":
            import msvcrt
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        taken = True
    return not taken


def _record_path() -> str:
    # Beside the lock, not inside it: a Windows lock is mandatory, so a reader could not open the locked byte.
    return os.path.join(os.path.dirname(lock_path()), "engine.json")


def _read() -> dict:
    try:
        with open(_record_path(), encoding="utf-8") as fh:
            return json.loads(fh.read() or "{}")
    except (OSError, ValueError) as e:
        return {"error": str(e)}


def hold(root: str) -> dict | None:
    """Take the lock for this process. None on success; otherwise the holder's record ({pid, root, since})."""
    global _held
    path = lock_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fh = open(path, "a+", encoding="utf-8")
    if not _try_lock(fh):
        fh.close()
        return _read()
    _held = fh
    with open(_record_path(), "w", encoding="utf-8") as rec:
        rec.write(json.dumps({"pid": os.getpid(), "root": root, "since": time.strftime("%Y-%m-%d %H:%M:%S")}))
    return None


def holder() -> dict | None:
    """Who holds the lock right now, or None if no engine is alive. Asking takes the lock for an instant."""
    path = lock_path()
    if not os.path.exists(path):
        return None
    with open(path, "a+", encoding="utf-8") as fh:
        if _try_lock(fh):
            return None   # free: closing the file releases it again
    return _read()
