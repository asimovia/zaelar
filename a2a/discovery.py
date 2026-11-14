"""Discovery: hash the identifiers, publish our own, look up our contacts', turn a MUTUAL match into a proposal.

Hash scheme (MK-2): ``HMAC-SHA256(key="meshkore-people-v1", msg=value)`` lowercase hex, email lowercased and trimmed,
phone in E.164. A name is never a key (I4). A match only PROPOSES (D10): the request leaves on the owner's yes.

    PUT    /v1/people/me      {hashes ≤ 16}        → {hashes: n}
    DELETE /v1/people/me                           → opt-out
    POST   /v1/people/lookup  {hashes ≤ 100}       → [{hash, did, agent_id}]   (mutual matches only)
"""
from __future__ import annotations

import hashlib
import hmac
import re

from .transport.http import SignedHttp

HASH_KEY = b"meshkore-people-v1"
MAX_PUBLISHED = 16
MAX_LOOKUP = 100


def norm_email(v: str) -> str | None:
    v = (v or "").strip().lower()
    return v if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v) else None


def norm_phone(v: str, default_cc: str = "") -> str | None:
    """E.164. `default_cc` (e.g. "34") is applied to a national number; without it a number lacking `+` is refused
    rather than guessed."""
    raw = (v or "").strip()
    digits = re.sub(r"[^\d+]", "", raw)
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if not digits.startswith("+"):
        if not default_cc:
            return None
        digits = "+" + default_cc + digits.lstrip("0")
    body = digits[1:]
    return digits if body.isdigit() and 8 <= len(body) <= 15 else None


def hash_value(normalised: str) -> str:
    return hmac.new(HASH_KEY, normalised.encode(), hashlib.sha256).hexdigest()


def hashes_for(emails=(), phones=(), default_cc: str = "") -> dict[str, str]:
    """→ {hash: "email"|"phone"}; invalid values are skipped."""
    out: dict[str, str] = {}
    for e in emails or ():
        n = norm_email(e)
        if n:
            out[hash_value(n)] = "email"
    for p in phones or ():
        n = norm_phone(p, default_cc)
        if n:
            out[hash_value(n)] = "phone"
    return out


class HttpDirectory:
    def __init__(self, http: SignedHttp):
        self.http = http

    def publish(self, hashes: list[str]) -> int:
        r = self.http.request("PUT", "/v1/people/me", {"hashes": list(hashes)[:MAX_PUBLISHED]}) or {}
        return int(r.get("hashes", 0))

    def unpublish(self) -> None:
        self.http.request("DELETE", "/v1/people/me")

    def lookup(self, hashes: list[str]) -> list[dict]:
        out: list[dict] = []
        hs = list(hashes)
        for i in range(0, len(hs), MAX_LOOKUP):
            out.extend(self.http.request("POST", "/v1/people/lookup", {"hashes": hs[i:i + MAX_LOOKUP]}) or [])
        return out
