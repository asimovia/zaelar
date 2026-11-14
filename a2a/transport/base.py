"""The transport contract the library speaks. Two implementations: `fake.FakeNetwork` (in-process, the lab and the
tests) and the MeshKore HTTP clients (`mailbox.py`, `../discovery.py::HttpDirectory`, `live.py`).

Every method either returns its documented value or raises `TransportError` with the HTTP-like `status` — the
library turns that into one event and keeps its cadence (I6: fail open, never break)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class TransportError(Exception):
    def __init__(self, status: int, message: str = ""):
        super().__init__(f"{status} {message}".strip())
        self.status = status


@dataclass
class Mail:
    seq: int
    from_did: str
    ts: int
    body: dict


@dataclass
class LiveShare:
    share_id: str
    push_token: str
    expires_at: float
    ring: int = 500


@dataclass
class IncomingShare:
    share_id: str
    from_did: str
    expires_at: float
    read_token: str


class Mailbox(Protocol):
    def post(self, to_did: str, wire: dict) -> int: ...
    def pull(self, after: int | None = None, limit: int = 50) -> list[Mail]: ...
    def ack(self, upto: int) -> int: ...
    def set_policy(self, external: str = "closed", categories: list[str] | None = None) -> dict: ...


class Directory(Protocol):
    def publish(self, hashes: list[str]) -> int: ...
    def unpublish(self) -> None: ...
    def lookup(self, hashes: list[str]) -> list[dict]: ...      # [{hash, did, agent_id}]


class Live(Protocol):
    def open(self, to_did: str, ttl_s: int = 7200, ring: int = 500) -> LiveShare: ...
    def incoming(self) -> list[IncomingShare]: ...
    def push(self, share_id: str, push_token: str, sample: dict) -> int: ...
    def read(self, share_id: str, read_token: str, after: int = 0, limit: int = 100) -> dict: ...
    def close(self, share_id: str, push_token: str) -> None: ...
