"""The RELAY link to his daemon (V2-575 · P3): the second transport behind `nucleo/browser_window.py`, for an engine
that does not run on his computer.

An engine in a container cannot reach his loopback. His daemon dials OUT to a relay; this engine reaches it through
the service it already reports to, with the credential it already holds (the same `CONTROL_PLANE_URL` +
`X-Service-Token` pair the Energy lease uses):

    POST <service>/daemon/command  {op, args, deadline_ms}  → {ok, data | error}
    GET  <service>/daemon/presence                          → {connected, caps, version, platform, since}

If `CONTROL_PLANE_URL` is not set (every self-hosted engine), nothing here runs and the reach is exactly what it was.

WHAT IT DOES, mirroring the loopback link (`daemon_link.py`):
  · `sync()` reads presence and registers the daemon with `browser_window.daemon_connected(caps, opener)` when it is
    connected and declares `browser.auth`; it withdraws ONLY its own registration.
  · the opener sends `browser.open {url, task_id}` — never a `profile`: the window opens on the daemon's own profile,
    and the relay drops the field anyway.
  · `watch()` polls `browser.state`; two signed-in reads in a row → `browser.export_session {site}` (that ONE site's
    session from the daemon's own profile) → imported into this engine's browser (`owner_page._import_session`) →
    `browser.close` → the same `_auth_done` a local window ends with. Presence is re-read every `PRESENCE_POLL_S` while
    it waits; a daemon gone for two reads in a row gives the tasks back.

No cookie name or value is logged here: the import answers counts.
"""
from __future__ import annotations

import os

from widgets.navegador import owner as _o

#: Presence is re-read this often while a sign-in waits on his daemon.
PRESENCE_POLL_S = 30.0
_CMD_TIMEOUT_S = 35.0
_OPEN_DEADLINE_MS = 60_000
_EXPORT_DEADLINE_MS = 45_000

_state: dict = {"registered": False, "presence": {}}


def _is_cloud() -> bool:
    try:
        from nucleo.energy import account as cloud_account
        return bool(cloud_account.is_cloud_account())
    except Exception as e:  # noqa: BLE001 — unknown deployment: no relay is asked
        _o.logger.debug(f"relay_link: deployment unknown ({type(e).__name__})")
        return False


def _service() -> tuple[str, dict]:
    """(base URL, auth headers) of the service this engine reports to — the lease's pair; ("", {}) when none."""
    base = (os.getenv("CONTROL_PLANE_URL") or "").strip().rstrip("/")
    token = (os.getenv("CONTROL_PLANE_SERVICE_TOKEN") or "").strip()
    return base, ({"X-Service-Token": token} if token else {})


def hosted() -> bool:
    """This engine runs away from him and has a service to reach his daemon through."""
    return _is_cloud() and bool(_service()[0])


async def _http(method: str, path: str, body: dict | None = None, *, timeout: float = _CMD_TIMEOUT_S) -> tuple[int, dict]:
    """One request to the service: `(status, body)`; `(0, {})` when it cannot be reached. The one HTTP seam."""
    import httpx
    base, headers = _service()
    if not base:
        return 0, {}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await (client.get(base + path, headers=headers) if method == "GET"
                       else client.post(base + path, headers=headers, json=body or {}))
        try:
            data = r.json()
        except Exception:   # noqa: BLE001
            data = {}
        return r.status_code, data if isinstance(data, dict) else {}
    except Exception:       # noqa: BLE001 — unreachable: the caller decides what that means
        return 0, {}


async def command(op: str, args: dict | None = None, *, deadline_ms: int = 30_000) -> dict:
    """Run `op` on his daemon. Always `{ok, data}` or `{ok: False, error: {code, message}}`."""
    status, body = await _http("POST", "/daemon/command", {"op": op, "args": args or {}, "deadline_ms": deadline_ms},
                               timeout=deadline_ms / 1000.0 + 5.0)
    if status == 0:
        return {"ok": False, "error": {"code": "unreachable", "message": "the relay could not be reached"}}
    if status == 504:
        return {"ok": False, "error": {"code": "deadline_exceeded", "message": "the daemon did not answer in time"}}
    if not isinstance(body.get("ok"), bool):
        return {"ok": False, "error": {"code": f"http_{status}", "message": "no answer from the relay"}}
    return body


async def presence() -> dict:
    status, body = await _http("GET", "/daemon/presence", timeout=5.0)
    return body if status == 200 else {}


async def paired() -> bool | None:
    """Does his account have a daemon credential? None when the service cannot say."""
    status, body = await _http("GET", "/daemon/credentials", timeout=5.0)
    if status != 200:
        return None
    rows = body.get("credentials") if isinstance(body.get("credentials"), list) else []
    return any(isinstance(r, dict) and not r.get("revoked_at") for r in rows)


async def sync() -> bool:
    """Register his relayed daemon with `browser_window` when it is connected and can open a window; withdraw OUR
    registration when it no longer is. Never clears a link another transport registered. Returns connected."""
    from nucleo import browser_window
    p = await presence() if hosted() else {}
    _state["presence"] = p
    caps = [str(c) for c in (p.get("caps") or [])] if p.get("connected") else []
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


async def status_view() -> dict:
    """What `/api/daemon/status` reports as `relay`."""
    p = await presence()
    _state["presence"] = p
    connected = bool(p.get("connected"))
    is_paired = await paired()
    return {"paired": connected if is_paired is None else bool(is_paired or connected), "connected": connected,
            "caps": [str(c) for c in (p.get("caps") or [])] if connected else [],
            "version": str(p.get("version") or ""), "platform": str(p.get("platform") or ""),
            "since": p.get("since") or None}


async def _open(url: str, task_id: str) -> bool:
    """The opener registered with `browser_window`: the window opens on his computer, on the daemon's own profile."""
    out = await command("browser.open", {"url": url, "task_id": task_id}, deadline_ms=_OPEN_DEADLINE_MS)
    return bool(out.get("ok"))


def watch(task_id: str, site: str) -> None:
    """Arm the watcher of the relayed window (the same slot `_arm_login_watch` uses, so a cancel ends either)."""
    old = _o._login_timeouts.pop(task_id, None)
    if old:
        old.cancel()
    t = _o.asyncio.create_task(_watch(task_id, site))
    _o._login_timeouts[task_id] = t
    _o._running.add(t)
    t.add_done_callback(_o._running.discard)


async def import_session(task_id: str, site: str) -> dict:
    """Ask his daemon for `site`'s session and import it into this engine's browser. Returns counts."""
    from widgets.navegador import tasks
    out = await command("browser.export_session", {"site": site}, deadline_ms=_EXPORT_DEADLINE_MS)
    data = out.get("data") if out.get("ok") and isinstance(out.get("data"), dict) else {}
    if not data:
        tasks.milestone(task_id, "⚠️ No pude traer la sesión desde tu ordenador")
        return {"ok": False, "cookies": 0, "origins": 0}
    counts = await _o._import_session(str(data.get("domain") or ""), data.get("storage_state") or {})
    if counts.get("ok"):
        tasks.milestone(task_id, "🔐 Sesión traída desde tu ordenador")
    return counts


async def _watch(task_id: str, site: str) -> None:
    """Every `_LOGIN_POLL` s: still wanted? still open? signed in (two reads in a row)? Bounded by `_LOGIN_TIMEOUT`;
    presence re-read every `PRESENCE_POLL_S`. Every ending but a sign-in closes the window and gives the tasks back."""
    from widgets.navegador import tasks
    from widgets.navegador.owner_login import daemon_link
    stable, waited, since_presence, gone = 0, 0.0, 0.0, 0
    try:
        while True:
            await _o.asyncio.sleep(_o._LOGIN_POLL)
            waited += _o._LOGIN_POLL
            since_presence += _o._LOGIN_POLL
            t = tasks.get(task_id)
            if not t or not t.get("awaiting_login"):
                if not t or t.get("status") in tasks.ENDED_STATES:
                    await command("browser.close", {"task_id": task_id})
                    await _o._abandon_login(task_id)
                return
            if since_presence >= PRESENCE_POLL_S:
                since_presence = 0.0
                gone = 0 if await sync() else gone + 1
                if gone >= 2:
                    tasks.milestone(task_id, "✖ Tu ordenador se desconectó")
                    await _o._abandon_login(task_id)
                    return
            out = await command("browser.state", {"task_id": task_id})
            state = out.get("data") if out.get("ok") and isinstance(out.get("data"), dict) else {}
            if state and not state.get("open"):
                tasks.milestone(task_id, "✖ La ventana de inicio de sesión se cerró")
                await _o._abandon_login(task_id)
                return
            stable = stable + 1 if (state and daemon_link._signed_in(state)) else 0
            if stable >= 2:
                tasks.milestone(task_id, "✅ Detecté que ya iniciaste sesión")
                await import_session(task_id, site)              # BEFORE closing: session cookies live in the window
                await command("browser.close", {"task_id": task_id})
                await _o._auth_done(task_id)
                return
            if waited >= _o._LOGIN_TIMEOUT:
                tasks.finish(task_id, "failed",
                             f"⏰ Cerré la ventana de inicio de sesión de {site}: nadie entró en "
                             f"{int(_o._LOGIN_TIMEOUT // 60)} min.")
                await command("browser.close", {"task_id": task_id})
                await _o._abandon_login(task_id)
                return
    except _o.asyncio.CancelledError:
        _o.logger.debug(f"relay_link: the sign-in watch of {task_id} was cancelled")
