"""connectors/music/placement.py — where the sound goes, and what is really sounding (V2-812).

A music request comes from a SCREEN (`voice.screens`: the voice holder for a spoken turn, the typing screen for a
typed one). A provider that plays on a device somewhere else (Spotify Connect) used to be picked whenever it was
connected and sent the song to its active device or the first one it listed — a computer at home while he listened
on his phone — and «ok» was only the API's 204. This module holds the three facts the facade needs to stop that:

  · THE ASKING SCREEN and its kind (`phone` / `computer`), read from `voice.screens`. Unknown (a test, an API call
    with no turn) means «no placement»: the facade keeps its old choice.
  · THE RECORD of what was last started and where — provider, device, screen, the words it was asked with. It lives
    in the music card's store next to the in-page player's own block, so the card and the brain read the same
    fact, and controls (pause, volume, next) go to the provider that is SOUNDING instead of the first connected.
  · Nothing else: which remote device sits with which screen is the provider's own knowledge (`device_near`), and
    whether it really sounds is the provider's own read-back (`confirm`).
"""
from __future__ import annotations

import logging
import time
import unicodedata

logger = logging.getLogger("zaelar.music")

_WID = "musica"
_KEY = "source"


def asking_screen() -> str:
    """The device id of the screen this request came from, or "" when nothing says (no turn, no voice holder)."""
    try:
        from voice import screens
        return screens.current() or ""
    except Exception as e:  # noqa: BLE001 — no screen registry is «unknown», never a failure
        logger.debug(f"music.placement: screen unreadable: {e!r}")
        return ""


def screen_kind(dev: str) -> str:
    """`phone` | `computer` | "" — the kind of screen a device id names (`voice.screens.surface`)."""
    try:
        from voice import screens
        return screens.surface(dev) if dev else ""
    except Exception:  # noqa: BLE001
        return ""


def norm(q: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFKD", q or "") if not unicodedata.combining(c))
    return " ".join(s.lower().split())


def recorded() -> dict:
    """The last start: {provider, device_id, device, screen, query, at}. {} when nothing was started."""
    try:
        from widgets import store
        rec = (store.load(_WID, {}) or {}).get(_KEY)
        return dict(rec) if isinstance(rec, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def record(provider: str, *, device_id: str = "", device: str = "", screen: str = "", query: str = "") -> None:
    """Write what was just started, and where. Read-modify-write under the card's own lock, so it never erases the
    in-page player's block written a moment before."""
    try:
        from widgets import store
        with store.mutating(_WID):
            db = store.load(_WID, {}) or {}
            db[_KEY] = {"provider": provider, "device_id": device_id, "device": device, "screen": screen,
                        "query": query, "at": int(time.time())}
            store.save(_WID, db)
    except Exception as e:  # noqa: BLE001 — a lost record degrades to the old choice, never breaks playback
        logger.warning(f"music.placement: record not written: {e!r}")
