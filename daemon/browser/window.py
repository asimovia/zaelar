"""One headed window at a time, on a persistent profile, driven from a thread of its own.

WHY A THREAD WITH ITS OWN LOOP. The HTTP server is `ThreadingHTTPServer`: every request is a fresh thread, and a
Playwright object belongs to the event loop that created it. So the browser lives on ONE long-lived thread with ONE
asyncio loop, and each route hands it a coroutine (`_submit`) and waits for the answer with a bound. A request thread
never touches a Playwright object.

ONE WINDOW. A sign-in is a person looking at a window; two at once is two half-finished sign-ins. Opening a window for
task B while task A's is open closes A's first — the engine serializes logins the same way (`_auth_active`), so this
only happens when the engine has already given up on A.

THE PROFILE. By default under the daemon's own state directory (`config/daemon/browser/profile`, 0700 like the rest).
A caller on this machine may name another profile directory — the engine on the same computer names ITS profile, so
the session lands where the task's own browser will read it after the window closes. The name must be an absolute,
symlink-free directory path; the relay (P3) must never forward it, because a remote caller has no business naming a
directory on this disk.
"""
from __future__ import annotations

import asyncio
import os
import threading
from pathlib import Path
from urllib.parse import urlsplit

from .. import paths
from ..fs.refusal import Refusal
from . import channel, status

#: What `/health` declares when this daemon can open a sign-in window (the engine reads the same string).
CAPABILITY = "browser.auth"

#: How long a request thread waits for the browser thread. Launching Chromium cold takes a few seconds.
_OPEN_TIMEOUT_S = 45.0
_STATE_TIMEOUT_S = 8.0
_NAV_TIMEOUT_MS = 20_000

#: The task name of a window the person opened from the tray rather than one a task asked for.
PERSON_TASK = "tray"


# Seams kept at their old names (tests and callers patch them here); the measuring lives in `channel` and `status`.
_playwright_cache_dirs = channel.cache_dirs


def _chromium_on_disk() -> bool:
    return bool(channel.chromium_dir())


def _chrome_executable() -> str:
    return channel.chrome_executable()


def _select() -> str:
    return channel.select(chrome=_chrome_executable, chromium=_chromium_on_disk)


def available() -> bool:
    """Can this daemon open a window? Playwright importable AND a browser to drive — the person's Google Chrome, or
    the Chromium the daemon downloaded. `ZAELAR_DAEMON_BROWSER=0` turns the capability off by hand (a machine where
    the person does not want windows opened for them)."""
    return status.describe(select=_select)["state"] == "ready"


#: Extra Chromium flags for the sign-in window. ⚠️ NEVER `--remote-debugging-port`: Playwright talks to the browser
#: over a PIPE it owns (`--remote-debugging-pipe`), which no other process on this computer can join. A debug PORT
#: would let any local process — any page's `fetch` included — drive a browser the person is signed in to.
LAUNCH_ARGS = ("--start-maximized",)


def launch_kwargs(chosen: str) -> dict:
    """What `launch_persistent_context` receives besides the profile. Pure, so the transport rule is testable."""
    kwargs = {"headless": False, "viewport": None, "args": list(LAUNCH_ARGS)}
    if chosen == "chrome":
        kwargs["channel"] = "chrome"
    return kwargs


def _check_url(url: str) -> str:
    parts = urlsplit((url or "").strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise Refusal("bad_url", "A sign-in window opens an http(s) address, and this is not one.")
    return parts.geturl()


def _check_profile(raw: str) -> Path:
    """The default profile, or the absolute symlink-free directory the caller named."""
    if not raw:
        d = paths.state_dir() / "browser" / "profile"
    else:
        d = Path(raw)
        if not d.is_absolute():
            raise Refusal("bad_profile", "A browser profile is named by an absolute path.")
        try:
            resolved = d.resolve()
        except OSError:
            raise Refusal("bad_profile", "That browser profile path cannot be resolved.") from None
        if resolved != d:
            raise Refusal("bad_profile", "A browser profile path may not go through a symbolic link or '..'.")
        if d.exists() and not d.is_dir():
            raise Refusal("bad_profile", "That browser profile path is a file, not a folder.")
    try:
        d.mkdir(parents=True, exist_ok=True)
        os.chmod(d, 0o700)
    except OSError:
        raise Refusal("bad_profile", "The browser profile folder cannot be created.") from None
    return d


async def _launch_playwright(profile: Path):
    """The real launcher: a headed Chrome (or the downloaded Chromium) on a persistent profile. Returns
    `(context, stopper)`."""
    from playwright.async_api import async_playwright   # optional dependency — only reached when available()
    chosen = _select()
    pw = await async_playwright().start()
    try:
        kwargs = launch_kwargs(chosen)
        try:
            ctx = await pw.chromium.launch_persistent_context(str(profile), **kwargs)
        except Exception:
            # Playwright's `channel="chrome"` looks only where Chrome installs by default; a Chrome in
            # `~/Applications` (or wherever the registry says) is launched by its path instead.
            exe = _chrome_executable() if chosen == "chrome" else ""
            if not exe:
                raise
            kwargs.pop("channel", None)
            ctx = await pw.chromium.launch_persistent_context(str(profile), executable_path=exe, **kwargs)
    except Exception:
        await pw.stop()
        raise

    async def stop():
        try:
            await ctx.close()
        finally:
            await pw.stop()
    return ctx, stop


class Windows:
    """The one sign-in window. `launcher(profile) -> (context, stop)` is injectable so the contract is testable without
    a real Chromium; the context needs `pages`, `new_page()` and `cookies()`."""

    def __init__(self, launcher=None):
        self._launcher = launcher or _launch_playwright
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._start_lock = threading.Lock()
        self._current: dict = {}     # task, profile, context, stop, page, baseline

    # ── the browser thread ──────────────────────────────────────────────────────────────────────────────

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._start_lock:
            if self._loop is None:
                loop = asyncio.new_event_loop()
                t = threading.Thread(target=loop.run_forever, name="daemon-browser", daemon=True)
                t.start()
                self._loop, self._thread = loop, t
            return self._loop

    def _submit(self, coro, timeout: float):
        fut = asyncio.run_coroutine_threadsafe(coro, self._ensure_loop())
        try:
            return fut.result(timeout=timeout)
        except Refusal:
            raise
        except Exception as e:   # noqa: BLE001 — a launch that failed is a refusal with a reason, not a 500
            fut.cancel()
            raise Refusal("browser_failed", f"The browser window could not be opened here: {type(e).__name__}.") from None

    # ── coroutines (run on the browser thread only) ─────────────────────────────────────────────────────

    async def _fingerprint(self, ctx) -> set:
        try:
            return {(c.get("domain", ""), c.get("name", "")) for c in await ctx.cookies()}
        except Exception:   # noqa: BLE001 — a closed context has no cookies to count
            return set()

    async def _close_current(self) -> None:
        cur, self._current = self._current, {}
        stop = cur.get("stop")
        if stop is not None:
            try:
                await stop()
            except Exception:   # noqa: BLE001 — the person may have closed it already
                pass

    async def _open(self, task: str, url: str, profile: Path) -> dict:
        if self._current and self._current.get("task") != task:
            await self._close_current()
        if not self._current:
            ctx, stop = await self._launcher(profile)
            self._current = {"task": task, "profile": str(profile), "context": ctx, "stop": stop}
            self._current["baseline"] = await self._fingerprint(ctx)
        ctx = self._current["context"]
        page = ctx.pages[0] if getattr(ctx, "pages", None) else await ctx.new_page()
        self._current["page"] = page
        try:
            await page.goto(url, timeout=_NAV_TIMEOUT_MS)
        except Exception:   # noqa: BLE001 — a slow site still leaves a window the person can use
            pass
        try:
            await page.bring_to_front()
        except Exception:   # noqa: BLE001
            pass
        return {"ok": True, "task": task, "open": True}

    async def _state(self, task: str) -> dict:
        cur = self._current
        if not cur or cur.get("task") != task:
            return {"ok": True, "task": task, "open": False, "url": "", "new_cookies": 0}
        ctx = cur["context"]
        pages = list(getattr(ctx, "pages", None) or [])
        if not pages:
            # The person closed the window: nothing is left to watch, and the engine decides what that means.
            await self._close_current()
            return {"ok": True, "task": task, "open": False, "url": "", "new_cookies": 0, "closed_by_user": True}
        url = ""
        try:
            url = pages[-1].url or ""
        except Exception:   # noqa: BLE001
            pass
        new = await self._fingerprint(ctx) - cur.get("baseline", set())
        return {"ok": True, "task": task, "open": True, "url": url, "new_cookies": len(new)}

    async def _close(self, task: str) -> dict:
        if self._current and (not task or self._current.get("task") == task):
            await self._close_current()
        return {"ok": True, "task": task, "open": False}

    # ── the request-thread surface ──────────────────────────────────────────────────────────────────────

    def open(self, task: str, url: str, profile: str = "") -> dict:
        if not available() and self._launcher is _launch_playwright:
            raise Refusal("browser_unavailable",
                          "This daemon cannot open a browser window yet: no Google Chrome, and its Chromium is not "
                          "downloaded.")
        task = (task or "").strip()[:128]
        if not task:
            raise Refusal("bad_task", "A sign-in window belongs to a task; none was named.")
        return self._submit(self._open(task, _check_url(url), _check_profile(profile)), _OPEN_TIMEOUT_S)

    def open_for_person(self) -> dict:
        """The tray's «Sign-in window»: an empty window on the daemon's own profile, for a person who wants to sign
        in to a site before any task asks. Never another profile — the tray has no caller to name one."""
        if not available() and self._launcher is _launch_playwright:
            raise Refusal("browser_unavailable", "This daemon cannot open a browser window yet.")
        return self._submit(self._open(PERSON_TASK, "about:blank", _check_profile("")), _OPEN_TIMEOUT_S)

    def current_task(self) -> str:
        """The task whose window is open, or "" — what the tray reads to say «open» or «close»."""
        return str((self._current or {}).get("task") or "")

    def state(self, task: str) -> dict:
        if self._loop is None:
            return {"ok": True, "task": task, "open": False, "url": "", "new_cookies": 0}
        return self._submit(self._state((task or "").strip()[:128]), _STATE_TIMEOUT_S)

    def close(self, task: str = "") -> dict:
        if self._loop is None:
            return {"ok": True, "task": task, "open": False}
        return self._submit(self._close((task or "").strip()[:128]), _STATE_TIMEOUT_S)


WINDOWS = Windows()
