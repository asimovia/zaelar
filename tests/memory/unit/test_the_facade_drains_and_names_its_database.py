"""The memory facade's two doors for the engine's own stores (V2-941): `drain` waits, bounded, for the queued writes;
`database` is the one SQLite a store with tables of its own keeps them in. Neither caller reaches into `memory.queue`
or `memory.db` any more (`test_memory_boundary`).

Disarm: `drain` that never reports a timeout, `database` that opens a second handle → red.
"""
from __future__ import annotations

import asyncio

from memory import api


class _Queue:
    def __init__(self, never: bool):
        self.never = never

    async def join(self):
        if self.never:
            await asyncio.Event().wait()


def test_drain_says_whether_the_writes_landed_in_time(monkeypatch):
    import memory.api as facade
    monkeypatch.setattr(facade, "get_queue", lambda: _Queue(False))
    assert asyncio.run(api.drain(0.5)) is True
    monkeypatch.setattr(facade, "get_queue", lambda: _Queue(True))
    assert asyncio.run(api.drain(0.05)) is False


def test_the_database_is_the_engines_one_handle():
    from memory.db import get_db
    assert api.database() is get_db()
