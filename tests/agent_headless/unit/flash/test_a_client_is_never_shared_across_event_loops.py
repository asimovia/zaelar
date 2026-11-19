"""An async client is never handed to a different event loop.

The fast model's client was cached process-wide by endpoint only. When the voice moved to another device the
session restarted on a new loop, got the client whose connection pool belonged to the old one, and every turn
failed with «Event … is bound to a different event loop» — the agent went silent until the process restarted.
"""
from __future__ import annotations

import asyncio

from nucleo.llm import loop_clients
from nucleo.llm.fast_client import FastClient
from nucleo.llm.model_spec import ModelSpec


def _get_or_build(cache: dict, key: tuple) -> object:
    cli = loop_clients.get(cache, key)
    if cli is None:
        cli = object()
        loop_clients.put(cache, key, cli)
    return cli


def test_the_same_loop_reuses_and_another_loop_gets_its_own():
    cache: dict = {}

    async def twice():
        return _get_or_build(cache, ("k",)), _get_or_build(cache, ("k",))

    a1, a2 = asyncio.run(twice())
    b1, _ = asyncio.run(twice())
    assert a1 is a2, "inside one loop the warm client is reused"
    assert b1 is not a1, "a new loop must never receive the previous loop's client"


def test_clients_of_a_closed_loop_are_dropped():
    cache: dict = {}
    async def build():
        return _get_or_build(cache, ("k",))

    asyncio.run(build())                     # that loop is closed when run() returns

    async def peek():
        return loop_clients.get(cache, ("k",))
    assert asyncio.run(peek()) is None
    assert not cache, "a closed loop's pool can never be used again — it must not stay cached"


def test_the_fast_client_goes_through_the_per_loop_cache(monkeypatch):
    seen = []
    monkeypatch.setattr(FastClient, "_client_key", lambda self, spec: ("https://x", "k", ()))
    monkeypatch.setattr(FastClient, "_clients", {})

    async def build():
        cli = FastClient()._client_for(ModelSpec.__new__(ModelSpec))
        seen.append(cli)
        return cli

    asyncio.run(build())
    asyncio.run(build())
    assert seen[0] is not seen[1]


def test_a_loop_still_alive_does_not_lend_its_client_to_another():
    """The real shape: the previous session's loop has not closed yet when the next one starts."""
    cache: dict = {}

    async def build():
        return _get_or_build(cache, ("k",))

    old = asyncio.new_event_loop()
    try:
        a = old.run_until_complete(build())
        b = asyncio.run(build())
        assert a is not b
    finally:
        old.close()


def test_a_loops_first_client_is_built_off_the_loop(monkeypatch):
    """G1 (2026-11-19): the first stream of a loop built its client ON the loop — the SDK import, the TLS context and
    its lazy resources held a cloud host's loop 1.0 s at boot (the prewarm's first stream). It is built in a thread,
    and the loop keeps beating meanwhile; the next stream of that loop reuses it."""
    import threading
    import time

    import openai
    built_on = []

    class _Slow:
        def __init__(self, **k):
            built_on.append(threading.current_thread() is threading.main_thread())
            time.sleep(0.3)

        @property
        def chat(self):
            async def create(**k):
                raise ValueError("no network in this test")
            return type("C", (), {"completions": type("R", (), {"create": staticmethod(create)})})

    monkeypatch.setattr(openai, "AsyncOpenAI", _Slow)
    monkeypatch.setattr(FastClient, "_client_key", lambda self, spec: ("https://x", "k", ()))
    monkeypatch.setattr(FastClient, "_clients", {})

    async def first_streams():
        gap, last = [0.0], [time.perf_counter()]

        async def beat():
            while True:
                await asyncio.sleep(0.01)
                now = time.perf_counter()
                gap[0], last[0] = max(gap[0], now - last[0]), now
        hb = asyncio.create_task(beat())
        for _ in range(2):
            try:
                async for _t in FastClient()._stream_inner([{"role": "user", "content": "hi"}],
                                                           spec=ModelSpec(model="m", api_key="k"), max_tokens=1):
                    pass
            except ValueError:
                pass
        hb.cancel()
        return gap[0]

    gap = asyncio.run(first_streams())
    assert built_on == [False], f"the client must be built once, in a thread (built on main thread: {built_on})"
    assert gap < 0.15, f"the event loop was held {gap:.2f}s while the client was built"
