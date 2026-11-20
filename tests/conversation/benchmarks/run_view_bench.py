"""What a run's store reads cost with the account's history (v3.1 B4c, the review's TE-1) — a bench, by request.

    ./.venv/bin/python -m tests.conversation.benchmarks.run_view_bench [--exchanges 6000 60000] [--runs 200]

Fills a fresh `zaelar.db` with N exchanges (an entry, a line and a closed request each), then times what a run reads
— the composer's view and the claims' evidence — over `--runs` reads. The rule: flat, p95 ≤ 5 ms, at any N.
"""
from __future__ import annotations

import argparse
import statistics
import tempfile
import time
from pathlib import Path

from conversation.composer.compose import view_from
from conversation.manager import claims as CL
from memory.db import Database
from nucleo.conversation_host.store import ZaelarStore
from tests.conversation.unit.test_a_run_reads_a_window_not_the_history import _history


def measure(exchanges: int, runs: int) -> dict:
    with tempfile.TemporaryDirectory() as d:
        db = Database(Path(d) / "z.db")
        try:
            _history(db, exchanges)
            store, ms = ZaelarStore(db), []
            for _ in range(runs):
                t0 = time.perf_counter()
                v = store.view("a")
                view_from(v, prefix="", now_ms=10 ** 9, window=12)
                CL.valid(v, 0)
                ms.append((time.perf_counter() - t0) * 1000)
        finally:
            db.close()
    ms.sort()
    return {"exchanges": exchanges, "p50_ms": round(statistics.median(ms), 2),
            "p95_ms": round(ms[int(0.95 * (len(ms) - 1))], 2), "max_ms": round(ms[-1], 2)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exchanges", type=int, nargs="+", default=[6000, 60000])
    ap.add_argument("--runs", type=int, default=200)
    a = ap.parse_args()
    for n in a.exchanges:
        print(measure(n, a.runs))


if __name__ == "__main__":
    main()
