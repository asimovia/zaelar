"""Remote browser: the one seam that decides whether a consumer launches its Chromium or reaches one over CDP (V2-918).

Nothing set → `local`: every consumer launches as before. `ZAELAR_BROWSER_CDP_URL` (a fixed endpoint) or
`ZAELAR_BROWSER_LEASE=1` (leased from `CONTROL_PLANE_URL` + `/browser/lease|renew` with the host's service token) →
`remote`: consumers connect over CDP and the engine launches NO Chromium; an unreachable browser is the named
`RemoteBrowserUnavailable`, never a local fallback. Detail: `.meshkore/docs/modules/zaelar-remote-browser.md`.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

logger = logging.getLogger(__name__)

LEASE_TTL_S = 600          # renewed only while used: a lease nobody uses lapses on its own
RENEW_AT = 0.5             # renew when less than this fraction is left AND it was used since the last renewal
CONNECT_TIMEOUT_MS = 20_000
LEASE_PATH, RENEW_PATH = "/browser/lease", "/browser/renew"


class RemoteBrowserUnavailable(RuntimeError):
    """Remote mode is configured and no remote browser could be reached. The message names why."""


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def mode() -> str:
    if _env("ZAELAR_BROWSER_CDP_URL") or _env("ZAELAR_BROWSER_LEASE").lower() in ("1", "true", "yes"):
        return "remote"
    return "local"


def is_remote() -> bool:
    return mode() == "remote"


_lease: dict = {}               # {machine_id, cdp_url, expires_at, used_at, renewed_at}
_locks: dict = {}               # one lock per event loop


async def _post(path: str, body: dict, timeout: float) -> tuple[int, dict]:
    import httpx
    url, token = _env("CONTROL_PLANE_URL").rstrip("/"), _env("CONTROL_PLANE_SERVICE_TOKEN")
    if not url or not token:
        raise RemoteBrowserUnavailable("remote browser: lease mode needs CONTROL_PLANE_URL and its service token")
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(url + path, json=body, headers={"X-Service-Token": token})
        data = r.json()
    except Exception as e:  # noqa: BLE001
        raise RemoteBrowserUnavailable(f"remote browser: control plane unreachable ({type(e).__name__})") from e
    return r.status_code, data if isinstance(data, dict) else {}


async def _lease_endpoint() -> str:
    now = time.time()
    if _lease.get("cdp_url") and now < float(_lease.get("expires_at") or 0) - 5:
        used_since = float(_lease.get("used_at") or 0) > float(_lease.get("renewed_at") or 0)
        if float(_lease["expires_at"]) - now >= LEASE_TTL_S * RENEW_AT or not used_since:
            return _lease["cdp_url"]
        status, data = await _post(RENEW_PATH, {"machine_id": _lease["machine_id"], "ttl_s": LEASE_TTL_S}, 10)
        if status == 200 and data.get("ok"):
            _lease.update(expires_at=float(data.get("expires_at") or _lease["expires_at"]), renewed_at=now)
            return _lease["cdp_url"]
    status, data = await _post(LEASE_PATH, {"ttl_s": LEASE_TTL_S}, 90)
    if status != 200 or not data.get("ok") or not data.get("cdp_url"):
        raise RemoteBrowserUnavailable(f"remote browser: lease refused ({status} {data.get('error') or 'no_answer'})")
    _lease.clear()
    _lease.update(machine_id=data.get("machine_id"), cdp_url=data["cdp_url"],
                  expires_at=float(data.get("expires_at") or now + LEASE_TTL_S), renewed_at=now, used_at=now)
    logger.info(f"remote browser: leased {data.get('machine_id')} ({data.get('source')}, {data.get('waited_ms')} ms)")
    return _lease["cdp_url"]


async def endpoint() -> str:
    """The CDP endpoint to connect to. Raises RemoteBrowserUnavailable when remote mode has none."""
    if _env("ZAELAR_BROWSER_CDP_URL"):
        return _env("ZAELAR_BROWSER_CDP_URL")
    if not is_remote():
        raise RemoteBrowserUnavailable("remote browser: not configured")
    lock = _locks.setdefault(asyncio.get_running_loop(), asyncio.Lock())
    async with lock:
        return await _lease_endpoint()


def touch() -> None:
    """A consumer used the browser: the lease may be renewed at its next check."""
    if _lease:
        _lease["used_at"] = time.time()


async def connect(pw):
    """`await connect(playwright)` → a Browser connected over CDP. Never launches anything."""
    url = await endpoint()
    try:
        browser = await pw.chromium.connect_over_cdp(url, timeout=CONNECT_TIMEOUT_MS)
    except Exception as e:  # noqa: BLE001
        _lease.clear()          # a leased endpoint that does not answer is spent: the next call leases another
        raise RemoteBrowserUnavailable(f"remote browser: CDP connect failed ({type(e).__name__})") from e
    touch()
    return browser


def alive(browser) -> bool:
    try:
        return browser is not None and browser.is_connected()
    except Exception as e:  # noqa: BLE001 — an unreadable handle is a dead one: the caller reconnects
        logger.debug(f"remote browser: connection state unreadable ({e!r})")
        return False
