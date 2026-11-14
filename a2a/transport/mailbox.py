"""The MeshKore mailbox (MK-1/MK-8) as a `Mailbox`.

    POST /v1/mail/:to_did      {kind, …opaque} ≤ 16 KB   → 201 {seq}
    GET  /v1/mail?after=&limit=                          → 200 [{seq, from_did, ts, body}] · 204 empty
    POST /v1/mail/ack          {upto}                    → {acked_upto}
    PUT  /v1/mail/me/policy    {external, categories}    → echo
"""
from __future__ import annotations

from .base import Mail
from .http import SignedHttp, did_path


class HttpMailbox:
    def __init__(self, http: SignedHttp):
        self.http = http

    def post(self, to_did: str, wire: dict) -> int:
        r = self.http.request("POST", f"/v1/mail/{did_path(to_did)}", wire, ok=(201, 200))
        return int((r or {}).get("seq", 0))

    def pull(self, after: int | None = None, limit: int = 50) -> list[Mail]:
        rows = self.http.request("GET", "/v1/mail", query={"after": after, "limit": limit}) or []
        return [Mail(int(m["seq"]), m["from_did"], int(m.get("ts", 0)), m.get("body") or {}) for m in rows]

    def ack(self, upto: int) -> int:
        r = self.http.request("POST", "/v1/mail/ack", {"upto": int(upto)})
        return int((r or {}).get("acked_upto", 0))

    def set_policy(self, external: str = "closed", categories: list[str] | None = None) -> dict:
        return self.http.request("PUT", "/v1/mail/me/policy",
                                 {"external": external, "categories": list(categories or [])}) or {}

    def server_key(self) -> dict:
        """`{alg, pubkey, did}` of the network key that signs wake pushes."""
        return self.http.request("GET", "/v1/a2a/server-key", signed=False) or {}
