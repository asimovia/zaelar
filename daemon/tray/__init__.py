"""The tray / menu-bar icon of the installed daemon — a VIEW of `/health` with a short menu, never a second owner of
state.

    model       what the menu shows, as plain data (pure; tested on every OS)
    controller  reads `/health`, builds the view, runs what the person picked
    macos       a menu-bar extra (`rumps`), template image, glyph per state, no Dock icon (`LSUIElement`)
    windows     a notification-area icon (`pystray` + `Pillow`), also used on Linux when a desktop provides one

KEPT OUT OF THE HEADLESS PATH. Nothing in `daemon/` imports this package at module level: `daemon.cli` imports it
inside the branch that starts the resident WITH a tray (`--tray`, the default only for the packaged binary). So
`python -m daemon` — the service the tests and a self-hoster run — never loads a GUI library, and a test holds it
there. The GUI libraries are imported inside `load()` for the same reason: a build without them falls back to the
headless service with one line saying why, instead of not starting.

The menu: Open Zaelar · Allowed folders… · Sign-in window (open / close — or the browser download, start / cancel,
while there is no browser yet) · Outbound tunnel: on / off (V2-836) · Check for updates · Quit.
"""
from __future__ import annotations

import sys


def load():
    """`(run, "")` with `run(controller) -> int` for this OS, or `(None, reason)` when no tray can be shown."""
    try:
        if sys.platform == "darwin":
            from . import macos as backend   # noqa: PLC0415
        else:
            from . import windows as backend   # noqa: PLC0415 — pystray covers Windows and Linux desktops
    except Exception as e:   # noqa: BLE001 — ImportError, or a GUI library that fails on this desktop
        return None, f"{type(e).__name__}: {e}"
    return backend.run, ""


def run(port: int, quit_fn=None) -> int | None:
    """Show the tray for the daemon on `port` until the person quits. None when no tray could be shown."""
    runner, reason = load()
    if runner is None:
        print(f"zaelar-daemon: no tray icon on this system ({reason}); running without one.", flush=True)
        return None
    from .controller import Controller   # noqa: PLC0415
    return runner(Controller(port, quit_fn=quit_fn))
