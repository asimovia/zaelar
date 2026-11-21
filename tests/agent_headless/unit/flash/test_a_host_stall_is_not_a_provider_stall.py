"""A body loop the host stopped is not a provider that stalled (E0, node 3.202).

Measured 2026-11-12: with the body's loop stopped 12–31 s by a host out of memory, the turn's silence deadline fired
(«turno ATASCADO»), the provider circuit relayed a healthy titular to the stand-in, and the perf verdict said «hidden
reasoning or provider queue». Three HTTP calls ended the same instant the loop woke — a slow provider does not
synchronise three answers. Now the stream gives the deadline back the seconds the loop was stopped (and only those),
so a stall that reaches the provider circuit is the provider's, and the verdict names the HOST first.

Disarms (each seen red): drop the `stalled_since` branch in `pipeline_stream` → (a) cuts the turn; restart the whole
deadline on every stall → (b) never cuts; the 60 s host guard back in `provider_chain.note_stall` → (c) counts no
streak; drop the `host` branch in `turn_perf.verdict` → (d).
"""
from __future__ import annotations

from collections import deque

import pytest

from nucleo.llm import provider_chain as pc
from nucleo.pulse import loop_lag


@pytest.fixture
def meter(monkeypatch):
    from nucleo.workers import envelope
    monkeypatch.setattr(envelope, "policy", lambda: {**envelope._DEFAULTS, "loop_lag_s": 1.0})
    monkeypatch.setattr(loop_lag, "_state", {"loops": set(), "last": 0.0, "worst": 0.0, "n": 0, "total_s": 0.0,
                                             "stalls": deque(maxlen=64), "last_stall": None})
    monkeypatch.setattr(loop_lag, "_say", lambda s, who="host": None)
    monkeypatch.setattr(loop_lag, "_shed", lambda s: None)
    return loop_lag


class _Decision:
    """The turn's one decision (V2-893 L2, `route_by_verdict.Turn`): the stream settles it before the release."""
    async def settle(self):
        return None


class _Hold:
    def __init__(self, *a, **k):
        self.unread, self.said, self.decision = "", [], _Decision()

    def say(self, text):
        if text:
            self.said.append(text)

    async def release(self, *a):
        return None


def test_the_provider_circuit_counts_a_stall_whose_loop_seconds_were_already_taken_out(meter, monkeypatch):
    """(c) a stall that reaches the circuit is net of the loop's stopped seconds, so it counts even when the loop
    hiccuped within the last minute (P2: one hiccup used to switch the relay off for 60 s)."""
    monkeypatch.setattr(pc, "_slow_streak", {})
    monkeypatch.setattr(pc, "pick", lambda role=None: {"name": "titular"})
    loop_lag.note(13.0)
    pc.note_stall(role=pc.ROLE_VOICE)
    assert pc._slow_streak == {"titular": 1}

