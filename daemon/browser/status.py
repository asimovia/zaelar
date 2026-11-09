"""What the daemon says about its browser in `/health`, and the one rule that decides `browser.auth`.

THE SHAPE (read by the engine's interface and by the tray — both views, neither owns it):

    "browser": {
        "state":    "ready" | "downloading" | "absent" | "unsupported",
        "channel":  "chrome" | "chromium" | "",     # what a window opens in; "" when nothing can open one
        "progress": 0-100,                           # the Chromium download; 100 when ready
        "size_mb":  float,                           # the download's size once Playwright has said it; else 0
        "error":    "..."                            # only after a download that failed
    },
    "unsupported_browsers": ["edge", "firefox", "safari"]

    ready        a window can open now (Google Chrome found, or the downloaded Chromium complete)
    downloading  no Chrome; the Chromium download is running
    absent       no Chrome and no Chromium yet; this daemon CAN fetch one (Playwright is here)
    unsupported  this daemon cannot open windows at all: Playwright is not part of it (the portable `.pyz`, a bare
                 `python -m daemon`), or the person turned windows off (`ZAELAR_DAEMON_BROWSER=0`)

`/health` is the one route without a token, so nothing here names a path, a profile or anything about the person:
which KIND of browser, and how far a download got.
"""
from __future__ import annotations

import os

from .. import config
from . import channel
from .download import DOWNLOAD


def disabled() -> bool:
    """The person's own off switch for windows on this computer."""
    return (os.environ.get("ZAELAR_DAEMON_BROWSER") or "").strip() == "0"


def remember(chosen: str) -> None:
    """Record the measured channel in `daemon.json` when it CHANGED — a write per change, never per `/health`."""
    try:
        if chosen in channel.CHANNELS and config.browser().get("channel") != chosen:
            config.save_browser(channel=chosen)
    except Exception:   # noqa: BLE001 — a record that could not be written does not change what is launchable
        pass


def describe(*, playwright=None, select=None, job=None) -> dict:
    """The `browser` object of `/health`. Probes are injectable for tests."""
    job = job or DOWNLOAD
    if disabled() or not (playwright or channel.playwright_present)():
        return {"state": "unsupported", "channel": "", "progress": 0, "size_mb": 0}
    snap = job.snapshot()
    if snap["state"] == "downloading":
        return {"state": "downloading", "channel": "chromium", "progress": snap["progress"],
                "size_mb": snap["size_mb"]}
    chosen = (select or channel.select)()
    if chosen:
        remember(chosen)
        size = snap["size_mb"] if chosen == "chromium" else 0
        return {"state": "ready", "channel": chosen, "progress": 100, "size_mb": size}
    out = {"state": "absent", "channel": "", "progress": snap["progress"], "size_mb": snap["size_mb"]}
    if snap.get("error"):
        out["error"] = snap["error"]
    return out


def health_fields() -> dict:
    """Everything the browser half adds to `/health`, ready to be merged into its body."""
    return {"browser": describe(), "unsupported_browsers": list(channel.UNSUPPORTED_BROWSERS)}


def launchable() -> bool:
    """Can a window open RIGHT NOW? The measured rule `browser.auth` hangs on."""
    return describe()["state"] == "ready"


def ensure_download() -> dict:
    """On the resident's start: with Playwright here, no browser to use and `auto_download` still on, begin the
    Chromium download in the background. Returns the browser object either way."""
    current = describe()
    if current["state"] == "absent" and config.browser().get("auto_download", True):
        DOWNLOAD.start()
        return describe()
    return current
