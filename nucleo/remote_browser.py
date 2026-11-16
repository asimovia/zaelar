"""Remote browser: ONE seam that decides whether this engine drives a Chromium it launches or one it reaches over CDP.

Every consumer of a browser (the navegador widget's task browser, the search/scrape/video Chromium) asks this module
first. Two modes, decided by configuration only:

  local   (default — nothing set): the consumer launches its own Chromium exactly as before. Self-hosting is unchanged.
  remote  the consumer connects over CDP and the engine launches NO Chromium of its own:
            · ZAELAR_BROWSER_CDP_URL=<http(s)://host:port[/prefix] | ws(s)://…>  — a fixed endpoint; or
            · ZAELAR_BROWSER_LEASE=1 — the endpoint is LEASED from the deployment's control plane
              (`CONTROL_PLANE_URL` + `/browser/lease`, with this host's `CONTROL_PLANE_SERVICE_TOKEN`), renewed while
              it is in use and released when it is not. The lease answers `{machine_id, cdp_url, expires_at}`.

In remote mode a browser that cannot be reached is a NAMED failure (`RemoteBrowserUnavailable`), never a silent
fallback to a local launch: a host configured not to run Chromium must not start one behind its operator's back.

What a remote browser does NOT carry, by construction: the on-disk persistent profile of local mode (sessions a site
remembered, accepted consent banners), the launch-time `--proxy-server` of the daemon tunnel (V2-836 — its forwarder
listens on this host's loopback, which a remote browser cannot reach), and a headed window. The consumers say so in
their own labels; restoring a saved session into a fresh context goes through the same `add_cookies` path the daemon
hand-over already uses.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

logger = logging.getLogger(__name__)

#: How long one lease is asked for; the engine renews it only while the browser is being used.
LEASE_TTL_S = 600
#: A lease is renewed when less than this fraction of it remains AND it was used since the last renewal.
RENEW_AT = 0.5
#: CDP connect timeout.
CONNECT_TIMEOUT_MS = 20_000
LEASE_PATH = "/browser/lease"
RENEW_PATH = "/browser/renew"
RELEASE_PATH = "/browser/release"


class RemoteBrowserUnavailable(RuntimeError):
    """Remote mode is configured and no remote browser could be reached. The message names why."""


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def mode() -> str:
    """'remote' when a fixed CDP endpoint or a leased one is configured; 'local' otherwise."""
    if _env("ZAELAR_BROWSER_CDP_URL"):
        return "remote"
    if _env("ZAELAR_BROWSER_LEASE").lower() in ("1", "true", "yes"):
        return "remote"
    return "local"


def is_remote() -> bool:
    return mode() == "remote"


# ─── the lease ───────────────────────────────────────────────────────────────────────────────────────────────────
_lease: dict = {}               # {machine_id, cdp_url, expires_at, used_at, renewed_at}
_lock: asyncio.Lock | None = None
_lock_loop = None


def _get_lock() -> asyncio.Lock:
    global _lock, _lock_loop
    loop = asyncio.get_running_loop()
    if _lock is None or _lock_loop is not loop:
        _lock, _lock_loop = asyncio.Lock(), loop
    return _lock


def _cp() -> tuple[str, str]:
    return _env("CONTROL_PLANE_URL").rstrip("/"), _env("CONTROL_PLANE_SERVICE_TOKEN")


async def _post(path: str, body: dict, timeout: float) -> tuple[int, dict]:
    import httpx
    url, token = _cp()
    if not url or not token:
        raise RemoteBrowserUnavailable("remote browser: lease mode needs CONTROL_PLANE_URL and its service token")
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(url + path, json=body, headers={"X-Service-Token": token})
    except Exception as e:  # noqa: BLE001
        raise RemoteBrowserUnavailable(f"remote browser: control plane unreachable ({type(e).__name__})") from e
    try:
        data = r.json()
    except Exception:  # noqa: BLE001
        data = {}
    return r.status_code, data if isinstance(data, dict) else {}


def _lease_live(now: float) -> bool:
    return bool(_lease.get("cdp_url")) and now < float(_lease.get("expires_at") or 0) - 5


async def _lease_endpoint() -> str:
    now = time.time()
    if _lease_live(now):
        left = float(_lease["expires_at"]) - now
        used_since = float(_lease.get("used_at") or 0) > float(_lease.get("renewed_at") or 0)
        if left < LEASE_TTL_S * RENEW_AT and used_since:
            status, data = await _post(RENEW_PATH, {"machine_id": _lease["machine_id"], "ttl_s": LEASE_TTL_S}, 10)
            if status == 200 and data.get("ok"):
                _lease["expires_at"] = float(data.get("expires_at") or _lease["expires_at"])
                _lease["renewed_at"] = now
                return _lease["cdp_url"]
            _lease.clear()          # over on the other side: lease a fresh one below
        else:
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
    """The CDP endpoint to connect to. Raises RemoteBrowserUnavailable in remote mode when there is none."""
    fixed = _env("ZAELAR_BROWSER_CDP_URL")
    if fixed:
        return fixed
    if not is_remote():
        raise RemoteBrowserUnavailable("remote browser: not configured")
    async with _get_lock():
        return await _lease_endpoint()


def touch() -> None:
    """A consumer used the browser: the lease may be renewed at its next check."""
    if _lease:
        _lease["used_at"] = time.time()


async def release() -> None:
    """Hand the leased browser back (its Machine is destroyed on the other side). Best effort."""
    mid = _lease.get("machine_id")
    _lease.clear()
    if not mid or _env("ZAELAR_BROWSER_CDP_URL"):
        return
    try:
        await _post(RELEASE_PATH, {"machine_id": mid}, 10)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"remote browser: release failed ({e!r}) — it ends at its TTL")


async def connect(pw):
    """`await connect(playwright)` → a connected Browser over CDP. Never launches anything."""
    url = await endpoint()
    try:
        browser = await pw.chromium.connect_over_cdp(url, timeout=CONNECT_TIMEOUT_MS)
    except Exception as e:  # noqa: BLE001
        # A leased endpoint that does not answer is spent: the next call leases another.
        _lease.clear()
        raise RemoteBrowserUnavailable(f"remote browser: CDP connect failed ({type(e).__name__})") from e
    touch()
    return browser


def alive(browser) -> bool:
    try:
        return browser is not None and browser.is_connected()
    except Exception:  # noqa: BLE001
        return False
