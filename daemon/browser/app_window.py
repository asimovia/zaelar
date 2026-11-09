"""«Open Zaelar»: the agent in an app-mode window — one window, no tabs, no address bar.

WHERE IT POINTS.
  · A LOCAL engine (one answering on loopback): its own interface. The address is `ZAELAR_ENGINE_URL` when set (it
    must be loopback — this window never opens a remote address it was not handed by the relay), else the engine's
    fixed port, `http://localhost:43917`. The engine is "here" when its `/healthz` answers.
  · Otherwise a REMOTE engine, reached through the relay: if `daemon.relay.login_link` exists and returns an address
    (a one-time sign-in link the relay obtained), that is opened. The module is imported LAZILY, inside the call:
    the relay is built separately, and this code must run identically on a daemon that does not have it yet.
  · Neither: the item is disabled with the reason, «pair with your cloud agent first».

HOW IT OPENS. The browser PROGRAM the daemon uses (the person's Google Chrome, or the downloaded Chromium — see
`channel`) is started directly with `--app=<url>` on the daemon's own app profile. No Playwright, no pipe, no
debug port: nothing is attached to this window at all. It is the person's agent in a window of its own, not a
browser the daemon drives, so it carries no automation banner and no other process can steer it.

THE PROFILE is its own folder (`config/daemon/browser/app-profile`) beside the sign-in window's. Chrome locks a
profile to one running process, and the agent's window must stay open while a sign-in window opens and closes.

ONE WINDOW. A second «Open Zaelar» while the first window's process is alive does nothing and says so: the
person already has it, and a second app window on the same agent is two conversations' worth of confusion.
"""
from __future__ import annotations

import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from .. import paths
from ..fs.refusal import Refusal
from . import channel

DEFAULT_LOCAL_URL = "http://localhost:43917"
PAIR_FIRST = "pair with your cloud agent first"
_LOOPBACK = {"localhost", "127.0.0.1", "::1", "[::1]"}
_PROBE_TIMEOUT_S = 0.8


def local_url() -> str:
    """The local engine's address: `ZAELAR_ENGINE_URL` when it is a loopback http(s) URL, else the fixed port."""
    raw = (os.environ.get("ZAELAR_ENGINE_URL") or "").strip().rstrip("/")
    if raw:
        parts = urlsplit(raw)
        if parts.scheme in ("http", "https") and (parts.hostname or "") in _LOOPBACK:
            return raw
    return DEFAULT_LOCAL_URL


def _probe(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/healthz", timeout=_PROBE_TIMEOUT_S) as resp:   # noqa: S310 — loopback
            return 200 <= resp.status < 500
    except Exception:   # noqa: BLE001 — not answering is the answer
        return False


def _relay_link() -> str:
    """The relay's one-time sign-in link, or "" — including when the relay module does not exist on this daemon."""
    try:
        from ..relay import login_link   # noqa: PLC0415 — optional module, built separately
    except Exception:   # noqa: BLE001 — ImportError, or a relay that fails to import: no remote target
        return ""
    try:
        fn = getattr(login_link, "login_link", None) or getattr(login_link, "get", None)
        url = str(fn() or "") if callable(fn) else ""
    except Exception:   # noqa: BLE001
        return ""
    return url if urlsplit(url).scheme == "https" or (urlsplit(url).hostname or "") in _LOOPBACK else ""


def target(*, probe=_probe, relay=_relay_link) -> dict:
    """Where «Open Zaelar» would go right now: `{"enabled", "where": "local"|"remote"|"", "url", "reason"}`."""
    local = local_url()
    if probe(local):
        return {"enabled": True, "where": "local", "url": local, "reason": ""}
    remote = relay()
    if remote:
        return {"enabled": True, "where": "remote", "url": remote, "reason": ""}
    return {"enabled": False, "where": "", "url": "", "reason": PAIR_FIRST}


def profile_dir() -> Path:
    d = paths.state_dir() / "browser" / "app-profile"
    try:
        d.mkdir(parents=True, exist_ok=True)
        os.chmod(d, 0o700)
    except OSError:
        pass
    return d


def command(exe: str, url: str, profile: Path) -> list[str]:
    """The exact argv. ⚠️ Never a `--remote-debugging-port`: this window has no automation of any kind."""
    return [exe, f"--app={url}", f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check"]


class AppWindow:
    """The one agent window. `popen`, `target_fn` and `exe_fn` are injectable for tests."""

    def __init__(self, popen=subprocess.Popen, target_fn=target, exe_fn=None):
        self._popen = popen
        self._target = target_fn
        self._exe = exe_fn or (lambda: channel.executable(channel.select()))
        self._proc = None

    def is_open(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def open(self) -> dict:
        if self.is_open():
            return {"ok": True, "open": True, "already": True}
        where = self._target()
        if not where["enabled"]:
            raise Refusal("not_paired", where["reason"])
        exe = self._exe()
        if not exe:
            raise Refusal("browser_unavailable", "There is no browser to open Zaelar in yet.")
        kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | \
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            kwargs["start_new_session"] = True
        self._proc = self._popen(command(exe, where["url"], profile_dir()), **kwargs)
        return {"ok": True, "open": True, "where": where["where"]}


APP = AppWindow()
