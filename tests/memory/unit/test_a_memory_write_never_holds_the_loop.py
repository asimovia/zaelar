"""A memory write is applied OFF the event loop, one at a time and in order (INI-042 #34).

The queue's single consumer used to call the writer on the loop: one write is an embedding request for the text and
one more per new concept, each a synchronous HTTP call, so the loop stood still for their sum (1.8 s measured on a
cloud host; 7.6 s in a sandbox with a 1.5 s embeddings endpoint). The consumer now awaits each write on ONE writer
thread: the serialisation is the same (the next write starts when the previous one ended), the loop keeps running,
and the vector-space guard runs where it always ran — inside the write, after its own embedding call.
"""
import asyncio
import json
import threading
import time

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import queue as memqueue
from memory import writer as memwriter
from memory.queue import MemoryQueue


async def _worst_gap(stop: asyncio.Event) -> float:
    """The longest the loop went without running a 10 ms sleeper: how long something held it."""
    worst, last = 0.0, time.monotonic()
    while not stop.is_set():
        await asyncio.sleep(0.01)
        now = time.monotonic()
        worst, last = max(worst, now - last), now
    return worst


def test_slow_writes_run_off_the_loop_one_at_a_time_and_in_order(monkeypatch):
    seen, state = [], {"running": 0, "peak": 0}

    def slow_write(text, **kwargs):
        state["running"] += 1
        state["peak"] = max(state["peak"], state["running"])
        seen.append((text, threading.get_ident()))
        time.sleep(0.25)                      # the embedding request
        state["running"] -= 1
        return len(seen)

    monkeypatch.setitem(memqueue._writer.OPS, "write", slow_write)

    async def main():
        q = MemoryQueue()
        await q.start()
        loop, stop = asyncio.get_running_loop(), asyncio.Event()
        gap = asyncio.create_task(_worst_gap(stop))
        futs = [loop.create_future() for _ in range(3)]
        for i, fut in enumerate(futs):
            q.submit("write", f"w{i}", future=fut)
        ids = await asyncio.gather(*futs)
        await q.join()
        stop.set()
        worst = await gap
        await q.stop()
        return ids, worst, threading.get_ident()

    ids, worst, loop_tid = asyncio.run(main())
    assert [t for t, _ in seen] == ["w0", "w1", "w2"] and ids == [1, 2, 3]       # in order, each with its own result
    assert state["peak"] == 1                                                    # never two writes at once
    assert all(tid != loop_tid for _, tid in seen)                               # none of them on the loop
    assert len({tid for _, tid in seen}) == 1                                    # one writer thread
    assert worst < 0.15, f"the loop stood still {worst:.2f} s while a write was applied"


def test_a_failed_write_reaches_its_future_and_the_next_one_still_runs(monkeypatch):
    def write(text, **kwargs):
        if text == "bad":
            raise ValueError("no")
        return 7

    monkeypatch.setitem(memqueue._writer.OPS, "write", write)

    async def main():
        q = MemoryQueue()
        await q.start()
        loop = asyncio.get_running_loop()
        bad, good = loop.create_future(), loop.create_future()
        q.submit("write", "bad", future=bad)
        q.submit("write", "good", future=good)
        out = await asyncio.gather(bad, good, return_exceptions=True)
        await q.stop()
        return out

    bad, good = asyncio.run(main())
    assert isinstance(bad, ValueError) and good == 7


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    yield memdb.get_db()
    memdb.reset_db()
    mememb.reset()


def test_a_vector_from_a_degraded_call_is_still_refused_when_the_write_runs_off_the_loop(fresh_db, monkeypatch):
    if not fresh_db.vec_available:
        pytest.skip("no sqlite-vec in this environment")
    real = mememb.embed

    def degraded(text):
        vec = real(text)
        monkeypatch.setattr(mememb, "last_degraded", True)     # the titular fell over IN this call
        return vec

    monkeypatch.setattr(mememb, "embed", degraded)
    monkeypatch.setattr(memwriter, "_embed_sig_ok", lambda: True)

    async def main():
        q = MemoryQueue()
        await q.start()
        fut = asyncio.get_running_loop().create_future()
        q.submit("write", "the harbour office closes at two on Fridays", level="long", kind="fact", future=fut)
        mid = await fut
        await q.stop()
        return mid

    mid = asyncio.run(main())
    row = fresh_db.query_one("SELECT meta FROM memories WHERE id=?", (mid,))
    assert json.loads(row["meta"])["embed_pending"] == "degraded"
    assert fresh_db.query_one("SELECT COUNT(*) c FROM vec_memories WHERE memory_id=?", (mid,))["c"] == 0
