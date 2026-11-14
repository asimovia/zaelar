"""The engine's HTTP face for A2A, framework-free so the server can mount it with one route (post-clean wiring):

    POST /api/a2a/wake   body {"kind": "mail"|"live"}, header MeshKore-Sig by the NETWORK key
                         (GET /v1/a2a/server-key) → 202 and one pull · 401 and nothing otherwise
    GET  /api/a2a/status loopback or `A2A_API_TOKEN` → the agent's status (no DIDs beyond 8 chars)
"""
from __future__ import annotations

import hmac
import json
import os
import threading
import time

from loguru import logger

from .identity import BadSignature, NonceWindow, verify_mk_sig

WAKE_PATH = "/api/a2a/wake"
WAKE_MAX_BYTES = 256          # {"kind": "mail"} is 16 bytes; anything near this is not a wake
WAKE_PER_SOURCE = 6           # FAILED attempts per source per window that still get an event; then 429
WAKE_GLOBAL = 60              # failed attempts of all sources together per window
WAKE_WINDOW_S = 60.0
WAKE_COALESCE_S = 5.0         # verified wakes closer than this share one pull


def wake_exempt(path: str, method: str, content_length: str | None, enabled: bool) -> bool:
    """Whether a request may skip the session/loopback admission to reach the wake handler.

    Trusts nothing: it only says "this is shaped like a wake", and the handler's signature check is the gate.
    Exact raw path (no prefix, no trailing slash, no dot segments), POST only, A2A on, and a declared
    Content-Length of at most `WAKE_MAX_BYTES` (a chunked body with no length is not exempt)."""
    if not enabled or path != WAKE_PATH or (method or "").upper() != "POST":
        return False
    cl = (content_length or "").strip()
    return cl.isdigit() and int(cl) <= WAKE_MAX_BYTES


class WakeGate:
    """Verifies first, limits only what failed. A wake signed by the pinned key is never refused for what others
    sent (behind a proxy every caller shares one peer address), and a failed attempt leaves nothing behind but a
    counted event. Safe to call from several threads."""

    def __init__(self, server_pub_b64: str | None, clock=None):
        self.server_pub = server_pub_b64
        self._clock = clock
        self._nonces = NonceWindow(clock=self._now)
        self._hits: dict[str, list[float]] = {}
        self._last_pull = float("-inf")
        self._lock = threading.Lock()

    def _now(self) -> float:
        return float(self._clock()) if self._clock else time.time()

    def _limited(self, source: str) -> bool:
        """The budget of FAILED attempts (their events and log lines); a verified wake never spends it."""
        now, cut = self._now(), self._now() - WAKE_WINDOW_S
        for k in list(self._hits):
            self._hits[k] = [t for t in self._hits[k] if t > cut]
            if not self._hits[k]:
                del self._hits[k]
        if sum(map(len, self._hits.values())) >= WAKE_GLOBAL:
            return True
        mine = self._hits.setdefault(source or "?", [])
        if len(mine) >= WAKE_PER_SOURCE:
            return True
        mine.append(now)
        return False

    def _verified_kind(self, sig: str | None, path: str, body: str) -> str | None:
        try:
            doc = json.loads(body or "{}") or {}
            kind = doc.get("kind", "mail") if isinstance(doc, dict) else None
            if kind not in ("mail", "live"):
                return None
            verify_mk_sig(sig, "POST", path, body or "", expected_pub_b64=self.server_pub, now=int(self._now()),
                          seen_nonces=self._nonces)
            return kind
        except (BadSignature, ValueError) as exc:
            logger.debug("a2a: wake not verified: {}", type(exc).__name__)
            return None

    def handle(self, jobs, headers: dict, body: str, path: str = WAKE_PATH, source: str = "") -> tuple[int, dict]:
        h = {k.lower(): v for k, v in (headers or {}).items()}
        if not self.server_pub:
            return 503, {"error": "wake unavailable"}           # unpinned key: refused before any crypto or pull
        if len((body or "").encode()) > WAKE_MAX_BYTES:
            return 413, {"error": "too large"}
        with self._lock:
            kind = self._verified_kind(h.get("meshkore-sig"), path, body)
            if kind is None:
                if self._limited(source):
                    return 429, {"error": "slow down"}        # past the budget: nothing is written
                failed = True
            else:
                failed = False
                coalesced = self._now() - self._last_pull < WAKE_COALESCE_S
                if not coalesced:
                    self._last_pull = self._now()
        if failed:
            jobs.agent.emit("wake", ok=False, sig_ok=False, wake_kind="")
            return 401, {"error": "MeshKore-Sig by the network key required"}
        jobs.agent.emit("wake", sig_ok=True, wake_kind=str(kind)[:8])
        if coalesced:
            return 202, {"coalesced": True}                   # a pull just ran; the wake only ever asks for one
        return 202, {"pulled": jobs.wake()}


def status_allowed(client_host: str, headers: dict) -> bool:
    if client_host in ("127.0.0.1", "::1", "localhost"):
        return True
    token = os.getenv("A2A_API_TOKEN", "")
    got = {k.lower(): v for k, v in (headers or {}).items()}.get("authorization", "")
    return bool(token) and hmac.compare_digest(got, f"Bearer {token}")
