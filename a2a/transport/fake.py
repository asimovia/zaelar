"""In-process network for the lab and the tests: one `FakeNetwork` (the server) and one `FakeTransport` per agent.

It reproduces the server rules the library depends on, so a test that passes here exercises the same edges:

- mailbox: monotonic `seq` per recipient, `after` defaults to the ack cursor, 16 KB cap, `kind` required,
  relationship rule (without «recipient wrote to sender before» only `connect.request` passes, 20/day), 204 → []
- people: ≤ 16 published hashes, mutual rule (B returned to A for h iff h ∈ B.published and B looked up one of
  A's hashes), the first side records interest and gets nothing
- live: needs the relationship, ttl 60–28800, ring 10–2000, ≤ 2 KB samples, only the last `ring` kept, closed → 404
"""
from __future__ import annotations

import json
import secrets
import time

from .base import IncomingShare, LiveShare, Mail, TransportError

MAIL_MAX = 16 * 1024
SAMPLE_MAX = 2 * 1024


class FakeNetwork:
    def __init__(self, clock=time.time, mutual: bool = True):
        self.clock = clock
        self.mutual = mutual
        self.agents: dict[str, str] = {}               # did → agent_id
        self.boxes: dict[str, list[Mail]] = {}
        self.next_seq: dict[str, int] = {}
        self.acked: dict[str, int] = {}
        self.peers: set[tuple[str, str]] = set()       # (owner, peer): owner has written to peer
        self.connects: dict[str, int] = {}
        self.published: dict[str, set[str]] = {}
        self.looked: dict[str, dict[str, float]] = {}  # did → {hash: ts}
        self.shares: dict[str, dict] = {}
        self.calls: list[tuple[str, str]] = []         # (did, op) — the lab's HTTP-call budget
        self.down = False

    def register(self, did: str, agent_id: str = "") -> None:
        self.agents[did] = agent_id or did[8:16]
        self.boxes.setdefault(did, [])
        self.next_seq.setdefault(did, 0)
        self.acked.setdefault(did, 0)

    def transport(self, did: str) -> "FakeTransport":
        self.register(did)
        return FakeTransport(self, did)

    def _check(self, did: str, op: str):
        self.calls.append((did, op))
        if self.down:
            raise TransportError(503, "network down")
        if did not in self.agents:
            raise TransportError(401, "not registered")


class FakeTransport:
    """Implements `Mailbox`, `Directory` and `Live` for one DID."""

    def __init__(self, net: FakeNetwork, did: str):
        self.net, self.did = net, did

    # mailbox -------------------------------------------------------------------------------------------------
    def post(self, to_did: str, wire: dict) -> int:
        n = self.net
        n._check(self.did, "mail.post")
        raw = json.dumps(wire, separators=(",", ":"))
        if len(raw.encode()) > MAIL_MAX:
            raise TransportError(413, "too big")
        if to_did not in n.agents:
            raise TransportError(404, "no mailbox")
        kind = wire.get("kind") if isinstance(wire, dict) else None
        if not isinstance(kind, str) or not kind:
            raise TransportError(400, "kind required")
        if (to_did, self.did) not in n.peers:
            if kind != "connect.request":
                raise TransportError(403, "no relationship")
            k = f"{self.did}:{int(n.clock() // 86400)}"
            n.connects[k] = n.connects.get(k, 0) + 1
            if n.connects[k] > 20:
                raise TransportError(429, "connect quota")
        n.next_seq[to_did] += 1
        seq = n.next_seq[to_did]
        n.boxes[to_did].append(Mail(seq, self.did, int(n.clock()), json.loads(raw)))
        n.peers.add((self.did, to_did))
        return seq

    def pull(self, after: int | None = None, limit: int = 50) -> list[Mail]:
        n = self.net
        n._check(self.did, "mail.pull")
        after = n.acked[self.did] if after is None else after
        return [m for m in n.boxes[self.did] if m.seq > after][: min(100, max(1, limit))]

    def ack(self, upto: int) -> int:
        n = self.net
        n._check(self.did, "mail.ack")
        n.acked[self.did] = max(n.acked[self.did], min(upto, n.next_seq[self.did]))
        n.boxes[self.did] = [m for m in n.boxes[self.did] if m.seq > n.acked[self.did]]
        return n.acked[self.did]

    def set_policy(self, external: str = "closed", categories: list[str] | None = None) -> dict:
        self.net._check(self.did, "mail.policy")
        return {"external": external, "categories": list(categories or [])}

    # directory -----------------------------------------------------------------------------------------------
    def publish(self, hashes: list[str]) -> int:
        self.net._check(self.did, "people.put")
        if len(hashes) > 16:
            raise TransportError(400, "≤ 16 hashes")
        self.net.published[self.did] = set(hashes)
        return len(hashes)

    def unpublish(self) -> None:
        self.net._check(self.did, "people.delete")
        self.net.published.pop(self.did, None)
        self.net.looked.pop(self.did, None)

    def lookup(self, hashes: list[str]) -> list[dict]:
        n = self.net
        n._check(self.did, "people.lookup")
        now = n.clock()
        mine = n.looked.setdefault(self.did, {})
        for h in hashes:
            mine[h] = now
        my_hashes = n.published.get(self.did, set())
        out = []
        for other, theirs in n.published.items():
            if other == self.did:
                continue
            for h in hashes:
                if h not in theirs:
                    continue
                looked_back = any(x in my_hashes and now - t < 30 * 86400
                                  for x, t in n.looked.get(other, {}).items())
                if looked_back or not n.mutual:
                    out.append({"hash": h, "did": other, "agent_id": n.agents.get(other, "")})
        return out

    # live ----------------------------------------------------------------------------------------------------
    def open(self, to_did: str, ttl_s: int = 7200, ring: int = 500) -> LiveShare:
        n = self.net
        n._check(self.did, "live.open")
        if (to_did, self.did) not in n.peers:
            raise TransportError(403, "no relationship")
        if not (60 <= ttl_s <= 28800 and 10 <= ring <= 2000):
            raise TransportError(400, "bad ttl/ring")
        sid = secrets.token_hex(8)
        share = {"from": self.did, "to": to_did, "push": secrets.token_hex(12), "read": secrets.token_hex(12),
                 "expires_at": n.clock() + ttl_s, "ring": ring, "samples": [], "seq": 0, "closed": False}
        n.shares[sid] = share
        return LiveShare(sid, share["push"], share["expires_at"], ring)

    def _share(self, sid: str, token: str, which: str) -> dict:
        s = self.net.shares.get(sid)
        if not s or s["closed"] or s["expires_at"] <= self.net.clock():
            self.net.shares.pop(sid, None)
            raise TransportError(404, "no such share")
        if token != s[which]:
            raise TransportError(401, "bad token")
        return s

    def incoming(self) -> list[IncomingShare]:
        n = self.net
        n._check(self.did, "live.list")
        now = n.clock()
        return [IncomingShare(sid, s["from"], s["expires_at"], s["read"]) for sid, s in n.shares.items()
                if s["to"] == self.did and not s["closed"] and s["expires_at"] > now]

    def push(self, share_id: str, push_token: str, sample: dict) -> int:
        self.net.calls.append((self.did, "live.push"))
        s = self._share(share_id, push_token, "push")
        if len(json.dumps(sample).encode()) > SAMPLE_MAX:
            raise TransportError(413, "sample too big")
        s["seq"] += 1
        s["samples"] = (s["samples"] + [{"seq": s["seq"], "ts": int(self.net.clock()), "body": sample}])[-s["ring"]:]
        return s["seq"]

    def read(self, share_id: str, read_token: str, after: int = 0, limit: int = 100) -> dict:
        self.net.calls.append((self.did, "live.read"))
        s = self._share(share_id, read_token, "read")
        rows = [x for x in s["samples"] if x["seq"] > after][:limit]
        return {"samples": rows, "cursor": rows[-1]["seq"] if rows else after, "expires_at": s["expires_at"],
                "closed": False}

    def close(self, share_id: str, push_token: str) -> None:
        self.net.calls.append((self.did, "live.close"))
        s = self._share(share_id, push_token, "push")
        s["closed"] = True
        self.net.shares.pop(share_id, None)
