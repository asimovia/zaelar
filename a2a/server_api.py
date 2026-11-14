"""The engine's HTTP face for A2A, framework-free so the server can mount it with one route (post-clean wiring):

    POST /api/a2a/wake   body {"kind": "mail"|"live"}, header MeshKore-Sig by the NETWORK key
                         (GET /v1/a2a/server-key) → 202 and one pull · 401 and nothing otherwise
    GET  /api/a2a/status loopback or `A2A_API_TOKEN` → the agent's status (no DIDs beyond 8 chars)
"""
from __future__ import annotations

import hmac
import json
import os
import time

from .identity import BadSignature, verify_mk_sig

WAKE_PATH = "/api/a2a/wake"
WAKE_MAX_BYTES = 256          # {"kind": "mail"} is 16 bytes; anything near this is not a wake
WAKE_PER_SOURCE = 6           # signed-or-not attempts per source per window, checked BEFORE any crypto
WAKE_GLOBAL = 60              # all sources together per window
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
    def __init__(self, server_pub_b64: str | None, clock=None):
        self.server_pub = server_pub_b64
        self._nonces: set[str] = set()
        self._clock = clock
        self._hits: dict[str, list[float]] = {}
        self._last_pull = float("-inf")

    def _now(self) -> float:
        return float(self._clock()) if self._clock else time.time()

    def _limited(self, source: str) -> bool:
        now, cut = self._now(), self._now() - WAKE_WINDOW_S
        for k in list(self._hits):
            self._hits[k] = [t for t in self._hits[k] if t > cut]
            if not self._hits[k]:
                del self._hits[k]
        mine = self._hits.setdefault(source or "?", [])
        if len(mine) >= WAKE_PER_SOURCE or sum(map(len, self._hits.values())) >= WAKE_GLOBAL:
            return True
        mine.append(now)
        return False

    def handle(self, jobs, headers: dict, body: str, path: str = WAKE_PATH, source: str = "") -> tuple[int, dict]:
        h = {k.lower(): v for k, v in (headers or {}).items()}
        if not self.server_pub:
            return 503, {"error": "wake unavailable"}           # unpinned key: refused before any crypto or pull
        if len((body or "").encode()) > WAKE_MAX_BYTES:
            return 413, {"error": "too large"}
        if self._limited(source):
            return 429, {"error": "slow down"}
        try:
            if not self.server_pub:
                raise BadSignature("no network key pinned")
            verify_mk_sig(h.get("meshkore-sig"), "POST", path, body or "", expected_pub_b64=self.server_pub,
                          now=int(self._clock()) if self._clock else None, seen_nonces=self._nonces)
            doc = json.loads(body or "{}") or {}
            kind = doc.get("kind", "mail") if isinstance(doc, dict) else None
            if kind not in ("mail", "live"):
                raise ValueError("kind")
        except (BadSignature, ValueError):
            jobs.agent.emit("wake", ok=False, sig_ok=False, wake_kind="")
            return 401, {"error": "MeshKore-Sig by the network key required"}
        if len(self._nonces) > 5000:
            self._nonces.clear()
        jobs.agent.emit("wake", sig_ok=True, wake_kind=str(kind)[:8])
        if self._now() - self._last_pull < WAKE_COALESCE_S:
            return 202, {"coalesced": True}                   # a pull just ran; the wake only ever asks for one
        self._last_pull = self._now()
        n = jobs.wake()
        return 202, {"pulled": n}


def status_allowed(client_host: str, headers: dict) -> bool:
    if client_host in ("127.0.0.1", "::1", "localhost"):
        return True
    token = os.getenv("A2A_API_TOKEN", "")
    got = {k.lower(): v for k, v in (headers or {}).items()}.get("authorization", "")
    return bool(token) and hmac.compare_digest(got, f"Bearer {token}")
