"""nucleo/workers/search_budget.py — how many web searches ONE errand may spend (audit V2-783 P1-6, plan item 9).

Search slowness was the judge's first family (175 of 745 findings) and nothing bounded a worker's query loop.
Measured over 190 recorded errands (`tests/runs/use_cases/sandbox/*`, «🌐 web» events per errand, 2026-10-18):
median 6 queries, p90 29, p95 38, max 61. The bound sits at the p95: it never touches the normal hunt and stops
the tail that searches on while the conversation has ended. Spent, the worker is told to deliver with what it
has — the rows it found are already on the sheet (`findings.hand_search_rows`), so stopping loses nothing.
"""
from __future__ import annotations

import threading

#: Web searches one errand may run through the worker bridge (p95 of the recorded errands).
MAX_QUERIES = 40
_MAX_TASKS = 256

_lock = threading.Lock()
_spent: dict[str, int] = {}


def spend(task_id) -> str:
    """Count one search for `task_id`. "" while within the budget; the refusal for the worker once it is spent."""
    tid = str(task_id or "")
    if not tid:
        return ""
    with _lock:
        while len(_spent) >= _MAX_TASKS and tid not in _spent:
            _spent.pop(next(iter(_spent)))
        _spent[tid] = _spent.get(tid, 0) + 1
        n = _spent[tid]
    if n <= MAX_QUERIES:
        return ""
    return (f"search budget spent: this errand has already run {MAX_QUERIES} web searches. Do not search again — "
            f"deliver now with the candidates you already have (they are on the sheet), and say what is "
            f"still unverified.")


def forget(task_id=None) -> None:
    with _lock:
        if task_id is None:
            _spent.clear()
        else:
            _spent.pop(str(task_id), None)
