"""Shared fixtures of the conversation suite: a controllable clock, telemetry into a list, both stores."""
from __future__ import annotations

import pytest

from conversation.store import MemoryStore


class ManualClock:
    """Wall and monotonic time that move only when the test says so."""

    def __init__(self, t0_ms: int = 1_800_000_000_000) -> None:
        self.wall0, self.mono = t0_ms, 0

    def now_ms(self) -> int:
        return self.wall0 + self.mono

    def mono_ms(self) -> int:
        return self.mono

    def advance(self, ms: int) -> None:
        self.mono += ms

    async def sleep_until(self, mono_ms: int) -> None:
        self.mono = max(self.mono, mono_ms)


class ListTelemetry:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict]] = []

    def emit(self, kind: str, label: str, payload: dict) -> None:
        self.events.append((kind, label, payload))

    def labels(self, kind: str | None = None) -> list[str]:
        return [f"{k}/{lab}" for k, lab, _ in self.events if kind is None or k == kind]


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock()


@pytest.fixture
def telemetry() -> ListTelemetry:
    return ListTelemetry()


def zaelar_store(path, store_class=None):
    """The host's `Store` over a `zaelar.db` of its own (`conv_*` rows), as the engine runs it."""
    from memory.db import Database
    from nucleo.conversation_host.store import ZaelarStore
    return (store_class or ZaelarStore)(Database(path))


@pytest.fixture(params=["memory", "zaelar"])
def store(request, tmp_path):
    s = MemoryStore() if request.param == "memory" else zaelar_store(tmp_path / "zaelar.db")
    yield s
    s.close()


@pytest.fixture
def ear(clock, telemetry):
    from conversation.config import Config
    from conversation.ear import Ear
    from conversation.telemetry import Emitter
    from conversation.types import Ids
    return Ear("acct-test", Config(), Emitter(telemetry, clock, "acct-test"), Ids())


@pytest.fixture
def book(store, clock, telemetry):
    from conversation.ledger import Book
    from conversation.telemetry import Emitter
    lease = store.acquire("acct-test", "test")
    b = Book(store, lambda: lease, "acct-test", Emitter(telemetry, clock, "acct-test"), clock)
    return b
