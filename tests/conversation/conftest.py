"""Shared fixtures of the conversation suite: a controllable clock, telemetry into a list, both stores."""
from __future__ import annotations

import pytest

from conversation.store import MemoryStore, SqliteStore


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


@pytest.fixture(params=["memory", "sqlite"])
def store(request, tmp_path):
    s = MemoryStore() if request.param == "memory" else SqliteStore(tmp_path / "conversation.db")
    yield s
    s.close()
