"""Every port call of the manager goes through here: a DEADLINE and a MEASURE.

`call(...)` awaits a port coroutine under `asyncio.wait_for` and emits `conv_run/port_slow` when it took longer
than `Config.port_budget_ms`; a timeout raises `PortTimeout`, which the run turns into a visible recovery. `stream`
does the same for the model's events, one deadline for the first and one for each next. `TimedStore` measures every
transaction of the store (synchronous by contract, local and short — a lock held for seconds is an event, not a
silence). Deadlines are wall-clock: a port that hangs hangs in real time.
"""
from __future__ import annotations

import asyncio
import time
from contextlib import contextmanager
from typing import AsyncIterator, Awaitable, Callable, TypeVar

from conversation.config import Config
from conversation.ports import Lease, Store
from conversation.telemetry import Emitter

T = TypeVar("T")


class PortTimeout(TimeoutError):
    def __init__(self, port: str, ms: int) -> None:
        super().__init__(f"{port} did not answer in {ms} ms")
        self.port = port


def _slow(em: Emitter, cfg: Config, port: str, ms: float, refs: dict | None = None, timed_out: bool = False) -> None:
    if ms > getattr(cfg, f"{port}_budget_ms", cfg.port_budget_ms) or timed_out:
        em.emit("conv_run", "port_slow", owner="manager", cause={"kind": "port", "ref": port}, refs=refs or {},
                trace=None if refs else f"port:{port}",       # outside a run, the port is its own flow
                port=port, ms=int(ms), timed_out=timed_out)


async def call(em: Emitter, cfg: Config, port: str, aw: Awaitable[T], timeout_ms: int,
               refs: dict | None = None) -> T:
    t0, timed_out = time.monotonic(), False
    try:
        return await asyncio.wait_for(aw, timeout=max(timeout_ms, 1) / 1000)
    except asyncio.TimeoutError as e:
        timed_out = True
        raise PortTimeout(port, timeout_ms) from e
    finally:
        _slow(em, cfg, port, (time.monotonic() - t0) * 1000, refs, timed_out)


async def stream(em: Emitter, cfg: Config, agen: AsyncIterator, refs: dict | None = None) -> AsyncIterator:
    """The model's events, each under its deadline (the first is allowed longer than the gaps)."""
    it, first, end = agen.__aiter__(), True, object()
    try:
        while True:
            ev = await call(em, cfg, "model", anext(it, end), cfg.model_first_ms if first else cfg.model_gap_ms, refs)
            if ev is end:
                return
            first = False
            yield ev
    finally:                                   # a deadline or a stop: the provider's stream is closed, never left open
        closer = getattr(it, "aclose", None)
        if closer is not None:
            await closer()


class TimedStore:
    """The `Store` port, every transaction and snapshot measured."""

    def __init__(self, store: Store, em: Emitter, cfg: Config) -> None:
        self._s, self._em, self._cfg = store, em, cfg

    def acquire(self, account: str, owner: str) -> Lease:
        return self._s.acquire(account, owner)

    def current(self, account: str):
        return self._s.current(account)

    def check(self, lease: Lease) -> None:
        self._s.check(lease)

    @contextmanager
    def tx(self, lease: Lease):
        t0 = time.monotonic()
        try:
            with self._em.deferred(), self._s.tx(lease) as t:   # no port inside: what it says waits for the commit
                yield t
        finally:
            _slow(self._em, self._cfg, "store", (time.monotonic() - t0) * 1000)

    def snapshot(self, account: str):
        t0 = time.monotonic()
        try:
            return self._s.snapshot(account)
        finally:
            _slow(self._em, self._cfg, "store", (time.monotonic() - t0) * 1000)

    def view(self, account: str):
        """What a run reads: no read happens here — each of the view's reads is one bounded query."""
        return self._s.view(account)

    def close(self) -> None:
        self._s.close()

    def __getattr__(self, name: str):          # the adapter's own extras (an audited store's log) stay reachable
        return getattr(self._s, name)


@contextmanager
def measured(em: Emitter, cfg: Config, port: str, refs: dict | None = None):
    """Measure a port call whose deadline the callee enforces itself (the gateway's dispatch)."""
    t0 = time.monotonic()
    try:
        yield
    finally:
        _slow(em, cfg, port, (time.monotonic() - t0) * 1000, refs)


def sync(em: Emitter, cfg: Config, port: str, fn: Callable[[], T]) -> T:
    """A synchronous port call (the mouth's duck / stop: immediate by contract), measured."""
    t0 = time.monotonic()
    try:
        return fn()
    finally:
        _slow(em, cfg, port, (time.monotonic() - t0) * 1000)
