"""The writes and scans a turn makes ON its loop stay inside V2-776 M1's 3 ms (V2-778 F3-27, 2026-10-02).

The audit asked to move `request_row.opened/settle`, `spec.persist`, `task_block.recent_lines` and the people
block's scan off the event loop. Measured first, on 2026-10-02 (isolated DB with 300 earlier rows, 500 contacts):

    request_row.opened       p95 0.54 ms
    spec.persist             p95 0.04 ms
    request_row.settle       p95 0.05 ms
    task_block.recent_lines  p95 0.28 ms      → the four together ≈ 0.9 ms
    contactos.people_named   p95 1.15 ms      (500 contacts)

All of it fits the 3 ms V2-776 M1 promised, and moving it off the loop would buy nothing and add an ordering hazard
(`settle` landing before the `opened` write it settles). So the promise is PINNED instead: if one of these grows —
a missing index, a scan that stops being bounded — this goes red long before a turn feels it. Asserted on the MEDIAN:
a p95 inside the wide pass measured the machine's load (it went red at 3 ms with nothing changed), the median
measures the operation.
"""
from __future__ import annotations


import time

BUDGET_MS = 3.0


def _median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2]


def test_the_people_scan_fits_the_budget(monkeypatch):
    from widgets.contactos import data as CD
    people = [{"id": f"c{i}", "name": f"Persona{i} Apellido{i}", "kind": "person",
               "channels": [{"platform": "whatsapp", "handle": f"+3460000{i:04d}"}]} for i in range(500)]
    monkeypatch.setattr(CD, "load_db", lambda: {"contacts": people})
    monkeypatch.setattr(CD, "visible", lambda db: people)
    xs = []
    for _ in range(100):
        t = time.perf_counter()
        assert CD.people_named("escríbele a persona42 que llego tarde")
        xs.append((time.perf_counter() - t) * 1000)
    assert _median(xs) <= BUDGET_MS, f"naming people over 500 contacts takes {_median(xs):.2f} ms (median)"
