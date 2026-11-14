"""Signed HTTP to the MeshKore network. One place builds paths, signs and maps errors.

- the DID in a path is percent-encoded (`quote(did, safe="")`) and the ENCODED path is what is signed
- the query string is not signed (the server signs `URL.pathname`)
- the body is sent byte-for-byte as it was hashed
- 5xx and network errors retry with backoff (2 tries); every failure raises `TransportError(status)`
"""
from __future__ import annotations

import json
import os
import time
from urllib.parse import quote, urlencode

from ..identity import Identity
from .base import TransportError

DEFAULT_BASE = "https://api.meshkore.com"


def api_base() -> str:
    return (os.getenv("A2A_API_BASE") or DEFAULT_BASE).rstrip("/")


def did_path(did: str) -> str:
    return quote(did, safe="")


class SignedHttp:
    def __init__(self, me: Identity | None, base: str | None = None, client=None, timeout: float = 10.0,
                 retries: int = 2, backoff_s: float = 0.5, sleep=time.sleep):
        import httpx
        self.me = me
        self.base = (base or api_base()).rstrip("/")
        self._client = client or httpx.Client(timeout=timeout)
        self._retries, self._backoff, self._sleep = retries, backoff_s, sleep

    def request(self, method: str, path: str, body=None, query: dict | None = None, signed: bool = True,
                bearer: str | None = None, ok=(200, 201, 204)):
        import httpx
        text = "" if body is None else json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        url = self.base + path + (("?" + urlencode({k: v for k, v in query.items() if v is not None}))
                                  if query else "")
        last: TransportError | None = None
        for attempt in range(self._retries):
            headers = {"content-type": "application/json"} if body is not None else {}
            if signed:
                if self.me is None:
                    raise TransportError(401, "no identity to sign with")
                headers["MeshKore-Sig"] = self.me.mk_sig(method, path, text)  # fresh nonce per attempt
            if bearer:
                headers["Authorization"] = f"Bearer {bearer}"
            try:
                r = self._client.request(method, httpx.URL(url), content=text.encode() if body is not None else None,
                                         headers=headers)
            except httpx.HTTPError as e:
                last = TransportError(0, type(e).__name__)
            else:
                if r.status_code in ok:
                    if r.status_code == 204 or not r.content:
                        return None
                    return r.json()
                try:
                    msg = r.json().get("error", "")
                except Exception:
                    msg = r.text[:200]
                last = TransportError(r.status_code, msg)
                if r.status_code < 500:
                    raise last
            if attempt + 1 < self._retries:
                self._sleep(self._backoff * (2 ** attempt))
        raise last or TransportError(0, "unreachable")
