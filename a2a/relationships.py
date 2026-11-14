"""Relationships: one row per peer DID and the handshake state machine.

    none ──connect()──▶ outgoing ──accept in──▶ accepted ──disconnect──▶ revoked
      │                    │  └──decline in──▶ declined
      └──request in──▶ incoming ──accept()──▶ accepted
                           └──decline()──▶ declined (declined_until = now + 30 d)

Crossing requests (both sides asked) resolve to `accepted` without a second card. A `connect.request` from the same
DID is honoured at most once per 24 h; after our decline it is dropped until `declined_until`.
"""
from __future__ import annotations

import secrets
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .store import JsonDoc

STATUSES = ("none", "outgoing", "incoming", "accepted", "declined", "revoked")
DECLINE_HOLD_S = 30 * 86400
REQUEST_EVERY_S = 86400
SEEN_MAX = 2000


class IllegalTransition(Exception):
    pass


@dataclass
class Relationship:
    did: str
    rel: str = field(default_factory=lambda: secrets.token_hex(6))
    contact_id: str = ""
    name: str = ""
    agent_id: str = ""
    status: str = "none"
    matched_by: str = ""
    since: float = 0.0
    declined_until: float = 0.0
    last_in: float = 0.0
    last_out: float = 0.0
    last_request_in: float = 0.0
    note: str = ""


class Relationships:
    def __init__(self, state_dir: Path, clock=time.time):
        self._doc = JsonDoc(Path(state_dir) / "relationships.json", {"peers": {}, "seen": [], "cursor": 0})
        self._clock = clock
        self._seen = deque(self._doc.data.get("seen", []), maxlen=SEEN_MAX)
        self._seen_set = set(self._seen)

    # rows ----------------------------------------------------------------------------------------------------
    def get(self, did: str) -> Relationship | None:
        row = self._doc.data["peers"].get(did)
        return Relationship(**row) if row else None

    def by_contact(self, cid: str) -> Relationship | None:
        for row in self._doc.data["peers"].values():
            if row.get("contact_id") == cid:
                return Relationship(**row)
        return None

    def all(self) -> list[Relationship]:
        return [Relationship(**r) for r in self._doc.data["peers"].values()]

    def put(self, r: Relationship) -> Relationship:
        self._doc.data["peers"][r.did] = asdict(r)
        self._doc.save()
        return r

    def ensure(self, did: str, **kw) -> Relationship:
        r = self.get(did) or Relationship(did=did)
        for k, v in kw.items():
            if v and hasattr(r, k):
                setattr(r, k, v)
        return self.put(r)

    # cursor + replay ---------------------------------------------------------------------------------------
    @property
    def cursor(self) -> int:
        return int(self._doc.data.get("cursor", 0))

    def set_cursor(self, seq: int) -> None:
        if seq > self.cursor:
            self._doc.data["cursor"] = int(seq)
            self._doc.save()

    def seen(self) -> set:
        return self._seen_set

    def mark_seen(self, env_id: str) -> None:
        if env_id in self._seen_set:
            return
        if len(self._seen) == self._seen.maxlen:
            self._seen_set.discard(self._seen[0])
        self._seen.append(env_id)
        self._seen_set.add(env_id)
        self._doc.data["seen"] = list(self._seen)
        self._doc.save()

    # transitions ---------------------------------------------------------------------------------------------
    def _move(self, did: str, allowed_from: tuple, to: str, **kw) -> Relationship:
        r = self.get(did) or Relationship(did=did)
        if r.status not in allowed_from:
            raise IllegalTransition(f"{r.status} → {to}")
        r.status = to
        for k, v in kw.items():
            if v or k in ("since", "declined_until"):
                setattr(r, k, v)
        return self.put(r)

    def outgoing(self, did: str, **kw) -> tuple[Relationship, bool]:
        """Our request. Returns (row, crossing): crossing=True when they had already asked us."""
        r = self.get(did)
        if r and r.status == "incoming":
            return self._move(did, ("incoming",), "accepted", since=self._clock(), **kw), True
        if r and r.status == "accepted":
            raise IllegalTransition("already accepted")
        return self._move(did, ("none", "outgoing", "declined", "revoked"), "outgoing", last_out=self._clock(),
                          **kw), False

    def incoming(self, did: str, rel: str = "", **kw) -> tuple[Relationship, str]:
        """Their request. Returns (row, outcome): outcome ∈ card | crossing | duplicate | rate_limited | held.
        A first contact adopts the requester's `rel` id, so both machines log the same relationship id."""
        now = self._clock()
        r = self.get(did) or Relationship(did=did, **({"rel": rel} if rel else {}))
        if r.status == "accepted":
            return r, "duplicate"
        if r.status == "declined" and r.declined_until > now:
            return r, "held"
        if r.last_request_in and now - r.last_request_in < REQUEST_EVERY_S:
            return r, "rate_limited"
        r.last_request_in = now
        r.last_in = now
        for k, v in kw.items():
            if v and not getattr(r, k):
                setattr(r, k, v)
        if r.status == "outgoing":
            r.status, r.since = "accepted", now
            self.put(r)
            return r, "crossing"
        r.status = "incoming"
        self.put(r)
        return r, "card"

    def accept(self, did: str) -> Relationship:
        return self._move(did, ("incoming",), "accepted", since=self._clock())

    def accepted_by_peer(self, did: str) -> Relationship:
        return self._move(did, ("outgoing", "accepted"), "accepted", since=self._clock(), last_in=self._clock())

    def decline(self, did: str) -> Relationship:
        return self._move(did, ("incoming",), "declined", declined_until=self._clock() + DECLINE_HOLD_S)

    def declined_by_peer(self, did: str) -> Relationship:
        return self._move(did, ("outgoing",), "declined")

    def revoke(self, did: str) -> Relationship:
        return self._move(did, ("accepted", "outgoing", "incoming"), "revoked")

    def touch_in(self, did: str) -> None:
        r = self.get(did)
        if r:
            r.last_in = self._clock()
            self.put(r)

    def touch_out(self, did: str) -> None:
        r = self.get(did)
        if r:
            r.last_out = self._clock()
            self.put(r)
