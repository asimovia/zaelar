"""What the tunnel carried, per destination HOST — the audit line the person can read (V2-836).

One audit line when a host is first reached in an hour, and one summary per host (streams, bytes each way) when the
hour turns or the tunnel closes. Never a URL, a path or a query: the tunnel cannot see them (TLS), and the host is
exactly what it can see. Refusals are audited too, collapsed per (host, reason) per hour, so a page that keeps asking
for a private address leaves one line saying so instead of a thousand.
"""
from __future__ import annotations

import threading
import time

from .. import audit

WINDOW_S = 3600.0


class Ledger:
    def __init__(self, clock=time.time, record=None):
        self._clock = clock
        self._record = record or audit.record
        self._lock = threading.Lock()
        self._hosts: dict[str, dict] = {}       # host → {first, last, streams, up, down}
        self._refused: dict[tuple[str, str], float] = {}

    def opened(self, host: str) -> None:
        now = self._clock()
        with self._lock:
            row = self._hosts.get(host)
            fresh = row is None or now - row["first"] >= WINDOW_S
            if fresh and row is not None:
                self._flush_one(host, row)
            if fresh:
                row = {"first": now, "last": now, "streams": 0, "up": 0, "down": 0}
                self._hosts[host] = row
            row["streams"] += 1
            row["last"] = now
        if fresh:
            self._record("egress.host", caller="relay", path=host, outcome="ok")

    def bytes(self, host: str, up: int = 0, down: int = 0) -> None:
        with self._lock:
            row = self._hosts.get(host)
            if row is not None:
                row["up"] += up
                row["down"] += down
                row["last"] = self._clock()

    def refused(self, host: str, code: str) -> None:
        now = self._clock()
        key = (host[:200], code)
        with self._lock:
            last = self._refused.get(key)
            if last is not None and now - last < WINDOW_S:
                return
            self._refused[key] = now
            if len(self._refused) > 4096:
                self._refused.clear()
        self._record("egress.host", caller="relay", path=host[:200] or None, outcome="refused", reason=code)

    def _flush_one(self, host: str, row: dict) -> None:
        self._record("egress.summary", caller="relay", path=host, outcome="ok",
                     detail={"streams": row["streams"], "bytes_out": row["up"], "bytes_in": row["down"]})

    def flush(self) -> None:
        """One summary line per host seen, then start over (the tunnel closed, or the switch went off)."""
        with self._lock:
            rows, self._hosts = self._hosts, {}
        for host, row in rows.items():
            self._flush_one(host, row)

    def hosts_last_hour(self) -> int:
        now = self._clock()
        with self._lock:
            return sum(1 for r in self._hosts.values() if now - r["last"] < WINDOW_S)


LEDGER = Ledger()
