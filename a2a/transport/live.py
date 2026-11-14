"""MeshKore live share (MK-10) as a `Live`: an ephemeral ring per share, capability tokens for samples.

    POST   /v1/live/:to_did          (sender sig)  {ttl_s, ring} → 201 {share_id, push_token, expires_at, ring}
    GET    /v1/live                  (recipient sig)            → [{share_id, from_did, expires_at, read_token}]
    POST   /v1/live/s/:id/samples    Bearer push_token, ≤ 2 KB  → {seq}
    GET    /v1/live/s/:id?after=     Bearer read_token          → {samples, cursor, expires_at, closed}
    GET    /v1/live/s/:id/stream     SSE (not used by the library: the reader polls; the viewer widget may stream)
    DELETE /v1/live/s/:id            Bearer push_token          → closes and wipes
"""
from __future__ import annotations

from urllib.parse import quote

from .base import IncomingShare, LiveShare
from .http import SignedHttp, did_path


class HttpLive:
    def __init__(self, http: SignedHttp):
        self.http = http

    def open(self, to_did: str, ttl_s: int = 7200, ring: int = 500) -> LiveShare:
        r = self.http.request("POST", f"/v1/live/{did_path(to_did)}", {"ttl_s": int(ttl_s), "ring": int(ring)},
                              ok=(201, 200)) or {}
        return LiveShare(r["share_id"], r["push_token"], float(r.get("expires_at", 0)), int(r.get("ring", ring)))

    def incoming(self) -> list[IncomingShare]:
        rows = self.http.request("GET", "/v1/live") or []
        return [IncomingShare(x["share_id"], x["from_did"], float(x.get("expires_at", 0)), x["read_token"])
                for x in rows]

    def push(self, share_id: str, push_token: str, sample: dict) -> int:
        r = self.http.request("POST", f"/v1/live/s/{quote(share_id, safe='')}/samples", sample, signed=False,
                              bearer=push_token) or {}
        return int(r.get("seq", 0))

    def read(self, share_id: str, read_token: str, after: int = 0, limit: int = 100) -> dict:
        return self.http.request("GET", f"/v1/live/s/{quote(share_id, safe='')}", query={"after": after,
                                 "limit": limit}, signed=False, bearer=read_token) or {"samples": []}

    def close(self, share_id: str, push_token: str) -> None:
        self.http.request("DELETE", f"/v1/live/s/{quote(share_id, safe='')}", signed=False, bearer=push_token)
