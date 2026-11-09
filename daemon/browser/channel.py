"""WHICH browser the daemon's windows open in — measured on this computer, never assumed.

TWO SOURCES, in this order:

  1. GOOGLE CHROME, if the person has it installed → Playwright's `channel="chrome"`. A real Chrome the person
     already trusts and keeps updated, nothing to download. Found where each OS puts it:
       macOS    `/Applications/Google Chrome.app` (or the per-user `~/Applications`)
       Windows  the `App Paths\\chrome.exe` registry key, then the `Program Files` / per-user install folders
       Linux    `google-chrome` (or `google-chrome-stable`) on PATH
  2. CHROMIUM downloaded by the daemon into Playwright's own cache (`~/Library/Caches/ms-playwright`,
     `%LOCALAPPDATA%\\ms-playwright`, `~/.cache/ms-playwright`) — the exact revision the bundled Playwright was built
     against, and only once its `INSTALLATION_COMPLETE` marker is there: a download that was cancelled halfway
     leaves a folder of the right name with half a browser in it.

ONLY GOOGLE CHROME IS SUPPORTED AS AN INSTALLED BROWSER. Edge is Chromium too and would probably work; "probably"
is not something to put in front of a person, and every browser added here is one more to verify on every release.
`UNSUPPORTED_BROWSERS` is published in `/health` so the interface can say so instead of leaving someone with Edge
wondering why the daemon wants to download a browser.

NEVER ANOTHER BROWSER'S PROFILE. Finding Chrome means finding its PROGRAM. The daemon always launches it on its own
profile directory; the person's everyday Chrome profile, its cookies and its passwords are never read.
"""
from __future__ import annotations

import glob
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

#: What `/health` lists as browsers the daemon will NOT use even when installed (v1 supports Google Chrome only).
UNSUPPORTED_BROWSERS = ["edge", "firefox", "safari"]

CHANNELS = ("chrome", "chromium")


# ── Google Chrome ─────────────────────────────────────────────────────────────────────────────────────────────

def _registry_chrome() -> str:
    """`HKCU`/`HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\chrome.exe` — where the Chrome
    installer records itself, whatever folder it chose. Windows only; "" anywhere else or on any error."""
    try:
        import winreg  # noqa: PLC0415 — Windows-only module
    except ImportError:
        return ""
    key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, key) as handle:
                value, _kind = winreg.QueryValueEx(handle, None)
                if value:
                    return str(value).strip().strip('"')
        except OSError:
            continue
    return ""


def chrome_candidates(platform: str | None = None, env=None, home: Path | None = None) -> list[str]:
    """The places Google Chrome lives on `platform`, most likely first. Pure: no disk is read."""
    platform = platform or sys.platform
    env = os.environ if env is None else env
    home = home or Path.home()
    if platform == "darwin":
        rel = "Google Chrome.app/Contents/MacOS/Google Chrome"
        return [f"/Applications/{rel}", str(home / "Applications" / rel)]
    if platform.startswith("win"):
        rel = os.path.join("Google", "Chrome", "Application", "chrome.exe")
        bases = [env.get("PROGRAMFILES"), env.get("PROGRAMFILES(X86)"), env.get("LOCALAPPDATA")]
        return [os.path.join(b, rel) for b in bases if b]
    return []


def chrome_executable(platform: str | None = None, *, exists=os.path.isfile, which=shutil.which,
                      registry=_registry_chrome, env=None, home: Path | None = None) -> str:
    """The Google Chrome program on this computer, or "". Every probe is injectable so each OS is testable on any."""
    platform = platform or sys.platform
    if platform.startswith("win"):
        found = registry()
        if found and exists(found):
            return found
    elif platform not in ("darwin",):
        for name in ("google-chrome", "google-chrome-stable"):
            found = which(name)
            if found:
                return found
        return ""
    for candidate in chrome_candidates(platform, env, home):
        if exists(candidate):
            return candidate
    return ""


# ── the downloaded Chromium ───────────────────────────────────────────────────────────────────────────────────

def cache_dirs() -> list[str]:
    """Where Playwright keeps its browsers on each OS (its own documented defaults), or the env override."""
    env = (os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or "").strip()
    if env and env != "0":
        return [env]
    home = Path.home()
    if sys.platform == "darwin":
        return [str(home / "Library" / "Caches" / "ms-playwright")]
    if sys.platform.startswith("win"):
        return [str(Path(os.environ.get("LOCALAPPDATA") or (home / "AppData" / "Local")) / "ms-playwright")]
    return [str(Path(os.environ.get("XDG_CACHE_HOME") or (home / ".cache")) / "ms-playwright")]


def playwright_present() -> bool:
    try:
        return importlib.util.find_spec("playwright") is not None
    except (ImportError, ValueError):
        return False


def chromium_revision() -> str:
    """The Chromium revision the BUNDLED Playwright drives (its `browsers.json`), or "" when unknown. A Chromium of
    another revision in the cache belongs to another Playwright and will not launch under this one."""
    try:
        spec = importlib.util.find_spec("playwright")
        locations = list(spec.submodule_search_locations or []) if spec else []
    except (ImportError, ValueError):
        return ""
    for base in locations:
        try:
            data = json.loads((Path(base) / "driver" / "package" / "browsers.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for entry in data.get("browsers") or []:
            if entry.get("name") == "chromium" and entry.get("revision"):
                return str(entry["revision"])
    return ""


def chromium_dir() -> str:
    """The COMPLETE Chromium install for this Playwright, or "". Completeness is Playwright's own marker file."""
    revision = chromium_revision()
    pattern = f"chromium-{revision}" if revision else "chromium-*"
    for cache in cache_dirs():
        for folder in sorted(glob.glob(os.path.join(cache, pattern)), reverse=True):
            if os.path.isfile(os.path.join(folder, "INSTALLATION_COMPLETE")):
                return folder
    return ""


def chromium_executable() -> str:
    """The program inside the downloaded Chromium (each platform's archive layout, old and new), or ""."""
    folder = chromium_dir()
    if not folder:
        return ""
    patterns = (
        "chrome-mac*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
        "chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
        "chrome-win*/chrome.exe",
        "chrome-linux*/chrome",
    )
    for pattern in patterns:
        hits = glob.glob(os.path.join(folder, pattern))
        if hits:
            return hits[0]
    return ""


# ── the choice ────────────────────────────────────────────────────────────────────────────────────────────────

def select(*, chrome=None, chromium=None) -> str:
    """"chrome", "chromium" or "" — the browser a window would open in right now. Measured every time: an installed
    Chrome wins, the downloaded Chromium is the fallback. What was chosen is RECORDED in `daemon.json`
    (`browser.channel`, see `status.remember`), never read back as an instruction — a stale record must not send a
    window to a browser that has since been uninstalled."""
    if (chrome or chrome_executable)():
        return "chrome"
    return "chromium" if (chromium or chromium_dir)() else ""


def executable(channel: str) -> str:
    """The program for `channel` — what the app window launches directly."""
    if channel == "chrome":
        return chrome_executable()
    if channel == "chromium":
        return chromium_executable()
    return ""
