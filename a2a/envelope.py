"""The A2A envelope: one signed, end-to-end encrypted JSON object per message, ≤ 16 KB on the wire.

Wire shape (what the mailbox stores; only `kind` is readable by the network, it needs it for its lane rules):

    {"v": "a2a/1", "kind": "msg.text", "id": "<hex16>", "ts": 1731600000,
     "from": "did:key:…", "to": "did:key:…", "sealed": {alg, n, ct}, "sig": "<b64>"}

`sig` is Ed25519 by `from` over the canonical JSON of every other field. `sealed` decrypts (with the pair's
X25519 key, salt = id, AAD = the canonical header) to the `body` object.
"""
from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass, field

from .identity import BadCiphertext, BadSignature, Identity, verify

VERSION = "a2a/1"
MAX_BYTES = 16 * 1024
FUTURE_SKEW_S = 5 * 60
MAX_AGE_S = 30 * 86400            # the mailbox retention; anything older is expired

# The kinds this library speaks. Unknown kinds are dropped by the dispatcher (never answered).
KINDS = (
    "connect.request", "connect.accept", "connect.decline", "connect.revoke",
    "msg.text",
    "grant.notice", "grant.revoked",
    "query", "reply", "denied",
    "live.offer", "live.closed",
)


class EnvelopeError(Exception):
    """A rejected envelope. `reason` is one of the `dropped` reasons of the events table."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _header(d: dict) -> dict:
    return {k: d[k] for k in ("v", "kind", "id", "ts", "from", "to")}


@dataclass
class Envelope:
    kind: str
    frm: str
    to: str
    body: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: secrets.token_hex(16))
    ts: int = field(default_factory=lambda: int(time.time()))

    def header(self) -> dict:
        return {"v": VERSION, "kind": self.kind, "id": self.id, "ts": self.ts, "from": self.frm, "to": self.to}

    # out -----------------------------------------------------------------------------------------------------
    def seal(self, me: Identity) -> dict:
        if me.did != self.frm:
            raise ValueError("an envelope is sealed by its sender")
        h = self.header()
        wire = dict(h, sealed=me.seal(self.to, canonical(self.body), salt=self.id, aad=canonical(h)))
        wire["sig"] = me.sign(canonical(wire))
        if len(canonical(wire)) > MAX_BYTES:
            raise EnvelopeError("oversize", f"{len(canonical(wire))} bytes")
        return wire

    # in ------------------------------------------------------------------------------------------------------
    @classmethod
    def open(cls, me: Identity, wire: dict, from_did: str | None = None, now: int | None = None,
             seen: "set | None" = None) -> "Envelope":
        """Verify and decrypt. `from_did` is the sender the TRANSPORT authenticated (the mailbox's `from_did`);
        it must match the envelope's own `from`. `seen` is the replay set (ids already processed)."""
        if not isinstance(wire, dict):
            raise EnvelopeError("malformed")
        if len(canonical(wire)) > MAX_BYTES:
            raise EnvelopeError("oversize")
        try:
            h = _header(wire)
            sig, sealed = wire["sig"], wire["sealed"]
        except (KeyError, TypeError):
            raise EnvelopeError("malformed") from None
        if h["v"] != VERSION:
            raise EnvelopeError("malformed", "version")
        if h["to"] != me.did:
            raise EnvelopeError("malformed", "not for me")
        if from_did is not None and from_did != h["from"]:
            raise EnvelopeError("bad_sig", "transport sender differs")
        unsigned = {k: v for k, v in wire.items() if k != "sig"}
        try:
            verify(h["from"], canonical(unsigned), sig)
        except (BadSignature, ValueError):
            raise EnvelopeError("bad_sig") from None
        now = int(time.time()) if now is None else now
        if not isinstance(h["ts"], int) or h["ts"] > now + FUTURE_SKEW_S:
            raise EnvelopeError("bad_sig", "future ts")
        if h["ts"] < now - MAX_AGE_S:
            raise EnvelopeError("expired")
        if seen is not None and h["id"] in seen:
            raise EnvelopeError("replay")
        try:
            body = json.loads(me.open(h["from"], sealed, salt=h["id"], aad=canonical(h)))
        except (BadCiphertext, ValueError):
            raise EnvelopeError("bad_sig", "cannot decrypt") from None
        if not isinstance(body, dict):
            raise EnvelopeError("malformed", "body")
        return cls(kind=h["kind"], frm=h["from"], to=h["to"], body=body, id=h["id"], ts=h["ts"])
