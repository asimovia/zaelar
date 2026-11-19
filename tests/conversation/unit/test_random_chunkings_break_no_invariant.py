"""P3, short profile (node 13.22): 2,000 seeded random conversations break none of I1–I9.

Each case cuts the voice at random (eager / resumed, an end of turn mid-sentence, a stream that stops), interleaves
typed texts from another device, stops, confirmations with and without a gesture, workers, contacts, reminders, jumps
of the clock and a takeover by another process, under a model that reads, writes, sends, claims numbers, stays silent
or fails, and injects new input between its own events. Fixed seeds, so a red names its seed and replays exactly:
`python -c "from conversation.testing.generate import run_case; print(run_case(<seed>))"`. The full 100,000-case run
is the bench (`tests/conversation/benchmarks/bombardment.py`), by request.
"""
from __future__ import annotations

import time

from conversation.testing.generate import run_case

CASES, ACTIONS, BUDGET_S = 2000, 10, 20.0


def test_two_thousand_random_conversations_break_no_invariant():
    t0, found = time.monotonic(), []
    for seed in range(CASES):
        violations = run_case(seed, ACTIONS)
        if violations:
            found.append((seed, violations[:3]))
            if len(found) >= 3:
                break
    assert not found, f"invariants broken (seed, first violations): {found}"
    assert time.monotonic() - t0 < BUDGET_S * 1.5, "the short profile outgrew its budget"
