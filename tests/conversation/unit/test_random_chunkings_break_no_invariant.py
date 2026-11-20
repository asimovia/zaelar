"""P3, short profile (node 13.22): 2,000 seeded random conversations break no invariant.

Each case cuts the voice at random (eager / resumed, an end of turn mid-sentence, a stream that stops) and delivers it
in the orders a real provider does — the end before the watermark passes the fall and the person going on at once, a
voice that does not fall between two pieces, an end with the voice up and its fall an instant later, a background with
words and no end — and interleaves typed texts from another device, stops, controls by id nobody handles, lines owed,
jumps of the clock and a takeover by another process, under a model that reads, asks for writes and sends, claims
numbers, stays silent or fails, and injects new input between its own events. Judged on what each case left: I1–I9,
every event in a flow, every request a run closed carries it, an entry in at most one batch that ended, nothing said
and no run started while his voice is open on the device of the batch's last entry (within the hold's bound), no
intervention gathering words past its maximum, and — once the signals stop — every request ended within its liveness.
Fixed seeds, so a red names its seed and replays exactly:
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
