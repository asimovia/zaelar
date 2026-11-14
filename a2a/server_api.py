"""The engine's HTTP face for A2A, framework-free so the server can mount it with one route (post-clean wiring):

    POST /api/a2a/wake   body {"kind": "mail"|"live"}, header MeshKore-Sig by the NETWORK key
                         (GET /v1/a2a/server-key) → 202 and one pull · 401 and nothing otherwise
    GET  /api/a2a/status loopback or `A2A_API_TOKEN` → the agent's status (no DIDs beyond 8 chars)
"""
from __future__ import annotations

import hmac
import json
import os

from .identity import BadSignature, verify_mk_sig

WAKE_PATH = "/api/a2a/wake"


class WakeGate:
    def __init__(self, server_pub_b64: str | None, clock=None):
        self.server_pub = server_pub_b64
        self._nonces: set[str] = set()
        self._clock = clock

    def handle(self, jobs, headers: dict, body: str, path: str = WAKE_PATH) -> tuple[int, dict]:
        h = {k.lower(): v for k, v in (headers or {}).items()}
        try:
            if not self.server_pub:
                raise BadSignature("no network key pinned")
            verify_mk_sig(h.get("meshkore-sig"), "POST", path, body or "", expected_pub_b64=self.server_pub,
                          now=int(self._clock()) if self._clock else None, seen_nonces=self._nonces)
            kind = (json.loads(body or "{}") or {}).get("kind", "mail")
        except (BadSignature, ValueError):
            jobs.agent.emit("wake", ok=False, sig_ok=False, wake_kind="")
            return 401, {"error": "MeshKore-Sig by the network key required"}
        if len(self._nonces) > 5000:
            self._nonces.clear()
        jobs.agent.emit("wake", sig_ok=True, wake_kind=str(kind)[:8])
        n = jobs.wake()
        return 202, {"pulled": n}


def status_allowed(client_host: str, headers: dict) -> bool:
    if client_host in ("127.0.0.1", "::1", "localhost"):
        return True
    token = os.getenv("A2A_API_TOKEN", "")
    got = {k.lower(): v for k, v in (headers or {}).items()}.get("authorization", "")
    return bool(token) and hmac.compare_digest(got, f"Bearer {token}")
