"""nucleo/net_probe.py — is the network back? Asked of the hosts the engine is CONFIGURED to talk to.

Measured 2026-10-20: a Wi-Fi switch took DNS down for 23 minutes; the session closed during it, memory
consolidation failed with «[Errno 8] nodename nor servname», and the heart card stayed red for the full 600 s TTL
of `voice/health_state.py` after the network was back — nothing cleared it, because the only clear for `memory`
is a later successful memory call, and with nobody speaking there is none. A network-class failure is a fact
about the CONNECTION, not about the provider, so it is re-checked against the connection.

The hosts come from the model table's titulars (`config/models.default.json`) — declared data, never a list
here. Blocking (DNS + one TCP connect); callers run it in a thread. Cached briefly so a polling panel does not
turn into a probe loop.
"""
from __future__ import annotations

import socket
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from loguru import logger

CACHE_S = 10.0
CONNECT_TIMEOUT_S = 1.5
_cache: dict = {"at": 0.0, "ok": False}


def _hosts() -> list[str]:
    from config import models
    seen: list[str] = []
    for name in models.services():
        host = urlparse(str(models.titular(name).get("base_url") or "")).hostname or ""
        if host and host not in ("localhost", "127.0.0.1", "::1") and host not in seen:
            seen.append(host)
    return seen


def _connects(host: str) -> bool:
    try:
        with socket.create_connection((host, 443), timeout=CONNECT_TIMEOUT_S):
            return True
    except OSError as e:
        logger.debug(f"net_probe: {host} does not answer ({e})")
        return False


def back() -> bool:
    """True only if EVERY configured remote host resolves and accepts a TCP connection on 443. One host is not
    enough: «connection refused» can be one provider down while the rest of the network works, and clearing that
    record would hide a real outage. Hosts are probed in parallel, so the wait is one timeout, not three."""
    now = time.monotonic()
    if now - _cache["at"] < CACHE_S:
        return _cache["ok"]
    try:
        hosts = _hosts()
        with ThreadPoolExecutor(max_workers=max(1, len(hosts))) as pool:
            ok = bool(hosts) and all(pool.map(_connects, hosts))
    except Exception as e:  # noqa: BLE001 — a probe that cannot run proves nothing either way
        logger.debug(f"net_probe: could not run ({e})")
        ok = False
    _cache.update(at=now, ok=ok)
    return ok
