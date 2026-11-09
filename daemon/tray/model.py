"""What the tray SHOWS, as plain data — computed from `/health` and nothing else.

Pure on purpose: no GUI library, no network, no disk. Both backends (`macos.py`, `windows.py`) render the same
`View`, and the tests read it on any OS. The tray never owns state: it renders what the daemon reports and calls
the daemon's own functions when the person picks an item.

THE GLYPH (three states; the icon changes shape, not only colour, so it reads in a monochrome menu bar):
    connected  the daemon answers and has nothing pending
    waiting    the daemon answers but is not finished: no folders chosen yet, or the browser is downloading
    error      the daemon does not answer its own `/health`
"""
from __future__ import annotations

from dataclasses import dataclass, field

STATES = ("connected", "waiting", "error")


@dataclass(frozen=True)
class Item:
    id: str
    label: str
    enabled: bool = True
    tooltip: str = ""


@dataclass(frozen=True)
class View:
    state: str
    title: str
    items: list = field(default_factory=list)


def glyph(health: dict | None) -> str:
    if not health or not health.get("ok"):
        return "error"
    browser = health.get("browser") or {}
    if browser.get("state") == "downloading" or not health.get("configured"):
        return "waiting"
    return "connected"


def _status_line(health: dict | None) -> str:
    if not health or not health.get("ok"):
        return "Zaelar — not running"
    version = health.get("version") or "?"
    browser = health.get("browser") or {}
    if browser.get("state") == "downloading":
        return f"Zaelar {version} — downloading the browser {int(browser.get('progress') or 0)}%"
    if not health.get("configured"):
        return f"Zaelar {version} — choose the folders it may read"
    return f"Zaelar {version} — running"


def _browser_item(health: dict, signin_task: str) -> Item:
    browser = health.get("browser") or {}
    state = browser.get("state")
    if state == "ready":
        return Item("signin", "Close sign-in window" if signin_task else "Open sign-in window")
    if state == "downloading":
        pct = int(browser.get("progress") or 0)
        size = browser.get("size_mb") or 0
        tail = f" of {size:.0f} MB" if size else ""
        return Item("download_cancel", f"Cancel browser download ({pct}%{tail})")
    if state == "absent":
        tip = "No Google Chrome on this computer: Zaelar downloads its own browser (about 170 MB)."
        return Item("download_start", "Download the browser for sign-ins…", True, tip)
    return Item("signin", "Sign-in window", False, "This build of Zaelar cannot open browser windows.")


def _update_item(health: dict) -> Item:
    """«Check for updates», or — once a verified update is waiting — the item that installs it."""
    update = health.get("update") or {}
    state = update.get("state")
    available = update.get("available") or {}
    if state == "ready" and available:
        return Item("update_install", f"Install Zaelar {available.get('version')} (build {available.get('build')}) "
                                      "and restart")
    if state == "downloading":
        return Item("updates", "Downloading the update…", False)
    return Item("updates", "Check for updates")


def view(health: dict | None, app_target: dict | None, signin_task: str = "") -> View:
    """The whole menu for one `/health` reading. `app_target` is `app_window.target()`'s answer."""
    state = glyph(health)
    items = [Item("status", _status_line(health), False)]
    if state == "error":
        items.append(Item("quit", "Quit Zaelar"))
        return View(state, items[0].label, items)
    target = app_target or {"enabled": False, "reason": ""}
    items += [
        Item("open", "Open Zaelar", bool(target.get("enabled")), str(target.get("reason") or "")),
        Item("folders", "Allowed folders…"),
        _browser_item(health, signin_task),
        _update_item(health),
        Item("quit", "Quit Zaelar"),
    ]
    return View(state, items[0].label, items)
