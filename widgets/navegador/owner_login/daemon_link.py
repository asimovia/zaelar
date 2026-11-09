"""The LOOPBACK link to the local daemon's browser (V2-575 · P2): the engine's half of «open the sign-in window on his
computer», when the daemon runs on the same machine.

WHERE IT PLUGS IN. `nucleo/browser_window.py` already answers where a window can open (`here` · `daemon` · ``) and
takes a transport's registration through `daemon_connected(capabilities, opener)`. This module IS such a transport,
for the loopback case: `sync()` asks the daemon's `/health` what it can do and registers it when it declares
`browser.auth`; `watch()` follows the window it opened until he has signed in, and hands the ending to the same
`_auth_done` / `_abandon_login` a local window ends with. The relay (P3) will be a second transport with the same two
calls; nothing here is the relay.

THE BACKEND SWITCH. `browser_backend()` is `daemon` only when a daemon is connected AND it is where the window goes
(`browser_window.reach() == DAEMON`), and `inproc` otherwise — so an engine with no daemon behaves exactly as before
(decision 5). An engine that has its OWN screen keeps its own window even with a daemon connected, on purpose: the
task's browser runs here, on this engine's profile, and a session created in another window is a session the task
cannot read.

THE PROFILE. Over loopback the daemon is on this machine, so the window opens on THIS engine's profile directory
(`launch_env._profile_dir`, locale-keyed): the engine stops its own headless browser first (one Chromium per
profile), he signs in, the window closes, and the engine's browser relaunches on the profile that now holds the
session. The cookies never leave this disk and never cross this module — the daemon answers how MANY appeared.

A CLOUD ENGINE NEVER PROBES 127.0.0.1: the daemon there would be somebody else's (same rule as `server/daemon_api.py`).
Never imports the daemon package: the two halves talk HTTP only (both directions are guarded by tests).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from widgets.navegador import owner as _o

_DEFAULT_PORT = 45817           # kept equal to `daemon.PORT` by a test, never imported
_TIMEOUT_S = 2.0
_OPEN_TIMEOUT_S = 50.0          # the daemon's own launch bound (45 s) plus slack

_state: dict = {"registered": False}


def _is_cloud() -> bool:
    try:
        from nucleo.energy import account as cloud_account
        return bool(cloud_account.is_cloud_account())
    except Exception:   # noqa: BLE001 — unknown deployment: treat as local, the probe is loopback-only anyway
        return False


def _config() -> dict:
    """`config/daemon/daemon.json` under the workspace, read WITHOUT creating anything; `{}` when absent."""
    try:
        from nucleo import workspace
        root = Path(workspace.root())
    except Exception:   # noqa: BLE001
        root = Path(os.getenv("ZAELAR_WORKSPACE") or Path(__file__).resolve().parents[3])
    try:
        data = json.loads((root / "config" / "daemon" / "daemon.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:   # noqa: BLE001 — nobody installed it: the normal case
        return {}


async def _call(path: str, payload: dict | None = None, *, timeout: float = _TIMEOUT_S) -> dict:
    """One loopback request to the daemon; `{}` when it cannot be reached or refuses."""
    import httpx
    cfg = _config()
    token = str(cfg.get("token") or "")
    if not token:
        return {}
    try:
        port = int(cfg.get("port") or _DEFAULT_PORT)
    except (TypeError, ValueError):
        port = _DEFAULT_PORT
    url = f"http://127.0.0.1:{port}{path}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            r = await (client.get(url, headers=headers) if payload is None
                       else client.post(url, headers=headers, json=payload))
        body = r.json() if r.content else {}
        return body if (r.status_code == 200 and isinstance(body, dict)) else {}
    except Exception:   # noqa: BLE001 — refused, timed out, no daemon: not reachable
        return {}


async def _open(url: str, task_id: str) -> bool:
    """The opener registered with `browser_window`: stop this engine's own browser (it holds the profile), then ask the
    daemon for a window on the same profile."""
    try:
        await _o.stop()
    except Exception:   # noqa: BLE001 — nothing was running
        pass
    _o._task_browsers.pop(task_id, None)
    body = await _call("/browser/open", {"task": task_id, "url": url, "profile": _o._profile_dir()},
                       timeout=_OPEN_TIMEOUT_S)
    return bool(body.get("ok"))


async def sync() -> bool:
    """Register the loopback daemon with `browser_window` when it declares the sign-in window; withdraw OUR
    registration when it no longer does. Never clears a link another transport registered. Returns connected."""
    from nucleo import browser_window
    caps: list = []
    if not _is_cloud():
        health = await _call("/health")
        if health.get("ok"):
            caps = [str(c) for c in (health.get("capabilities") or [])]
    if browser_window.BROWSER_CAPABILITY in caps:
        browser_window.daemon_connected(caps, opener=_open)
        _state["registered"] = True
        return True
    if _state["registered"]:
        browser_window.daemon_gone()
        _state["registered"] = False
    return False


def owns_link() -> bool:
    return bool(_state["registered"])


def browser_backend() -> str:
    """`daemon` when the sign-in window goes to a connected daemon, `inproc` otherwise (today's browser)."""
    from nucleo import browser_window
    return "daemon" if browser_window.reach() == browser_window.DAEMON else "inproc"


def watch(task_id: str, site: str) -> None:
    """Arm the watcher of the daemon's window (the same slot `_arm_login_watch` uses, so a cancel ends either)."""
    old = _o._login_timeouts.pop(task_id, None)
    if old:
        old.cancel()
    t = _o.asyncio.create_task(_watch(task_id, site))
    _o._login_timeouts[task_id] = t
    _o._running.add(t)
    t.add_done_callback(_o._running.discard)


def _signed_in(state: dict) -> bool:
    """The same versatile signal the local window uses (`_is_logged_in`): off the login/registration page AND at least
    one new cookie since the window opened."""
    from widgets.navegador import agent
    url = str(state.get("url") or "")
    if not url or agent._looks_like_login(url, "") or _o._REGISTER_TEXT_RE.search(url):
        return False
    return int(state.get("new_cookies") or 0) >= 1


async def _watch(task_id: str, site: str) -> None:
    """Every `_LOGIN_POLL` s: still wanted? still open? signed in (two reads in a row)? Bounded by `_LOGIN_TIMEOUT`.
    Every ending but a sign-in closes the window on his computer and gives the waiting tasks back."""
    from widgets.navegador import tasks
    stable, waited = 0, 0.0
    try:
        while True:
            await _o.asyncio.sleep(_o._LOGIN_POLL)
            waited += _o._LOGIN_POLL
            t = tasks.get(task_id)
            if not t or not t.get("awaiting_login"):
                if not t or t.get("status") in tasks.ENDED_STATES:
                    await _call("/browser/close", {"task": task_id})
                    await _o._abandon_login(task_id)
                return
            state = await _call("/browser/state", {"task": task_id})
            if state and not state.get("open"):
                tasks.milestone(task_id, "✖ La ventana de inicio de sesión se cerró")
                await _o._abandon_login(task_id)
                return
            stable = stable + 1 if _signed_in(state) else 0
            if stable >= 2:
                tasks.milestone(task_id, "✅ Detecté que ya iniciaste sesión")
                await _call("/browser/close", {"task": task_id})     # the profile is free again for the engine
                await _o._auth_done(task_id)
                return
            if waited >= _o._LOGIN_TIMEOUT:
                tasks.finish(task_id, "failed",
                             f"⏰ Cerré la ventana de inicio de sesión de {site}: nadie entró en "
                             f"{int(_o._LOGIN_TIMEOUT // 60)} min.")
                await _call("/browser/close", {"task": task_id})
                await _o._abandon_login(task_id)
                return
    except _o.asyncio.CancelledError:
        return
