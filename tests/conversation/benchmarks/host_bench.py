"""B1's bench: the conversation's thread over `zaelar.db`, with other writers loaded (by request, not in the gate).

    ./.venv/bin/python -m tests.conversation.benchmarks.host_bench [--seconds 20]

Two numbers, on a `zaelar.db` of its own: the latency of one transaction of the manager (p50 / p95 / max) while two
other threads write the same file the way the memory writer and the consolidator do (short transactions through
`Database.cursor()`, a burst every few ms), and the lag of an event loop in the main thread (the server's) — measured
with the conversation's thread running and without it. The claim it checks: a slow write holds the conversation's
thread, never the server's loop.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import tempfile
import threading
import time
from pathlib import Path

from memory.db import Database
from nucleo.conversation_host.store import ZaelarStore


def _load(db: Database, stop: threading.Event, burst: int, pause_s: float) -> None:
    n = 0
    while not stop.is_set():
        with db.cursor() as cur:
            for _ in range(burst):
                n += 1
                cur.execute("INSERT INTO sys_kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE "
                            "SET value=excluded.value", (f"bench:{n % 500}", "x" * 200))
        time.sleep(pause_s)


def _conversation(db: Database, stop: threading.Event, out: list) -> None:
    store = ZaelarStore(db)
    lease = store.acquire("bench", "host")
    i = 0
    while not stop.is_set():
        i += 1
        t0 = time.perf_counter()
        with store.tx(lease) as tx:
            tx.put("inbox", f"e{i}", {"state": "queued", "n": i})
            tx.scan("inbox", ("queued", "held"))
            tx.put("inbox", f"e{i}", {"state": "accounted", "n": i})
        out.append((time.perf_counter() - t0) * 1000)
        time.sleep(0.01)


async def _loop_lag(seconds: float) -> list[float]:
    lags, end = [], time.monotonic() + seconds
    while time.monotonic() < end:
        t0 = time.monotonic()
        await asyncio.sleep(0.01)
        lags.append((time.monotonic() - t0 - 0.01) * 1000)
    return lags


def _pct(xs: list[float], q: float) -> float:
    return round(sorted(xs)[min(len(xs) - 1, int(q * len(xs)))], 2) if xs else 0.0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seconds", type=float, default=20)
    args = ap.parse_args(argv)
    db = Database(Path(tempfile.mkdtemp(prefix="conv-bench-")) / "zaelar.db")
    report = {}
    for label, with_conv in (("loop_without_conversation", False), ("loop_with_conversation", True)):
        stop, txs = threading.Event(), []
        threads = [threading.Thread(target=_load, args=(db, stop, 50, 0.005), daemon=True),      # the writer
                   threading.Thread(target=_load, args=(db, stop, 400, 0.2), daemon=True)]      # the consolidator
        if with_conv:
            threads.append(threading.Thread(target=_conversation, args=(db, stop, txs), daemon=True))
        for t in threads:
            t.start()
        lags = asyncio.run(_loop_lag(args.seconds))
        stop.set()
        for t in threads:
            t.join(5)
        report[label] = {"lag_p50_ms": _pct(lags, .5), "lag_p95_ms": _pct(lags, .95), "lag_max_ms": round(max(lags), 2)}
        if with_conv:
            report["conversation_tx"] = {"n": len(txs), "p50_ms": _pct(txs, .5), "p95_ms": _pct(txs, .95),
                                         "max_ms": round(max(txs), 2), "mean_ms": round(statistics.mean(txs), 2)}
    db.close()
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
