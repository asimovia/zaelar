"""The tunnel token: `<instance_id>.<32 random bytes, base64url>` (V2-836).

The PREFIX is routing, not secret: the shared public hostname reads it to hand the daemon's WebSocket to the right
instance (`server/ingress.py`). The SECRET is the rest, and it is checked by THE INSTANCE THAT MINTED IT, against its
own in-memory set — so a forged prefix reaches an instance that does not know the token and closes the socket.

Short-lived (`TTL_S`), a handful outstanding at once (renewals overlap), compared in constant time, never logged and
never written to disk: a restart forgets them all, and the next offer mints a fresh one.
"""
from __future__ import annotations

import base64
import hmac
import os
import re
import threading
import time

TTL_S = 600.0
MAX_OUTSTANDING = 8
PREFIX_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

_lock = threading.Lock()
_outstanding: dict[str, float] = {}       # token → expires_at (epoch seconds)


def instance_id() -> str | None:
    """This instance's id, as the account routing knows it — or None (a self-hosted engine: no tunnel at all)."""
    try:
        from nucleo.energy import routing
        mid = routing.my_machine_id()
    except Exception:   # noqa: BLE001 — no routing module, no instance
        return None
    return mid if mid and PREFIX_RE.match(mid) else None


def prefix(token) -> str:
    """The instance a token names, or "" when it is not shaped like one."""
    if not isinstance(token, str) or "." not in token:
        return ""
    head = token.split(".", 1)[0]
    return head if PREFIX_RE.match(head) else ""


def mint(*, now: float | None = None, ttl: float = TTL_S, instance: str | None = None) -> tuple[str, float] | None:
    """A fresh token and when it expires, or None when this engine has no instance id."""
    inst = instance or instance_id()
    if not inst:
        return None
    t = time.time() if now is None else now
    token = f"{inst}.{base64.urlsafe_b64encode(os.urandom(32)).rstrip(b'=').decode('ascii')}"
    exp = t + ttl
    with _lock:
        for k in [k for k, e in _outstanding.items() if e <= t]:
            _outstanding.pop(k, None)
        while len(_outstanding) >= MAX_OUTSTANDING:
            _outstanding.pop(min(_outstanding, key=_outstanding.get), None)
        _outstanding[token] = exp
    return token, exp


def verify(token, *, now: float | None = None, instance: str | None = None) -> bool:
    """Is `token` one this instance minted, for itself, and not expired? Every outstanding token is compared, in
    constant time, so the answer's timing says nothing about how close a guess came."""
    inst = instance or instance_id()
    if not inst or not isinstance(token, str) or prefix(token) != inst:
        return False
    t = time.time() if now is None else now
    hit = False
    with _lock:
        for k, exp in list(_outstanding.items()):
            same = hmac.compare_digest(k.encode(), token.encode())
            if same and exp > t:
                hit = True
            if exp <= t:
                _outstanding.pop(k, None)
    return hit


def forget_all() -> None:
    with _lock:
        _outstanding.clear()
