"""A body loop the host stopped is not a provider that stalled (E0, node 3.202).

Measured 2026-11-12: with the body's loop stopped 12–31 s by a host out of memory, the turn's silence deadline fired
(«turno ATASCADO»), the provider circuit relayed a healthy titular to the stand-in, and the perf verdict said «hidden
reasoning or provider queue». Three HTTP calls ended the same instant the loop woke — a slow provider does not
synchronise three answers. Now the stream asks the body's own meter before declaring a stall, the provider circuit
counts no stall while the loop was stopped, and the verdict names the HOST first.

Disarms (each seen red): drop the `stalled_since` branch in `pipeline_stream` → (a) cuts the turn; drop the host guard
in `provider_chain.note_stall` → (b) counts the streak; drop the `host` branch in `turn_perf.verdict` → (c).
"""
from __future__ import annotations

import asyncio
from collections import deque
from types import SimpleNamespace

import pytest

from nucleo.flash import turn_perf as tp
from nucleo.llm import provider_chain as pc
from nucleo.pulse import loop_lag
from nucleo.turn import pipeline_stream as ps


@pytest.fixture
def meter(monkeypatch):
    from nucleo.workers import envelope
    monkeypatch.setattr(envelope, "policy", lambda: {**envelope._DEFAULTS, "loop_lag_s": 1.0})
    monkeypatch.setattr(loop_lag, "_state", {"loops": set(), "last": 0.0, "worst": 0.0, "n": 0, "total_s": 0.0,
                                             "stalls": deque(maxlen=64), "last_stall": None})
    monkeypatch.setattr(loop_lag, "_say", lambda s: None)
    monkeypatch.setattr(loop_lag, "_shed", lambda s: None)
    return loop_lag


class _Hold:
    def __init__(self, *a, **k):
        self.unread, self.said = "", []

    def say(self, text):
        if text:
            self.said.append(text)

    async def release(self, *a):
        return None


def _stream(emit, stall_at: float | None, chunk_at: float, quiet_ms: int = 200) -> dict:
    """One turn whose only chunk arrives at `chunk_at`; a host stall of 1.5 s is noted at `stall_at`."""
    buf: list[str] = []

    class FC:
        def stream(self, messages, spec=None, tools=None, on_tool_call=None, metrics=None):
            async def gen():
                await asyncio.sleep(chunk_at)
                yield "hola"
            return gen()

    async def run():
        if stall_at is not None:
            asyncio.get_running_loop().call_later(stall_at, lambda: loop_lag.note(1.5))
        return await ps.stream_the_reply(
            SimpleNamespace(_phase="answer", _death_logged=False),
            SimpleNamespace(_turn_budget_ms=lambda: quiet_ms, stream_advancing=lambda m, q: False, _WINDOW_MAX=10),
            FastClient=FC, messages=[], spec=None, _turn_tools=None, _on_tool_call=None, llm_metrics={}, _brief=None,
            send=lambda s: None, take=lambda final: "".join(buf), _buf_add=buf.append,
            speech=SimpleNamespace(inline=lambda s: s, sanitize=lambda s, drop_metadata=False: s), emit=emit,
            brain=SimpleNamespace(_window=[], _turn_calls=None), text="hola", spoken=[], first_ms=lambda: 0, t0=0.0,
            _dialog=None, data_done={}, _turn_op_tasks=[], _filler_audio=None)
    return asyncio.run(run())


def test_the_stream_waits_through_a_host_stall_instead_of_cutting_the_turn(meter, monkeypatch):
    """(a) the deadline fired while the loop was stopped: the wait goes on, the fact is said, the turn is not cut."""
    monkeypatch.setattr(ps._fup, "Hold", _Hold)
    monkeypatch.setattr(ps._route, "wait_s", lambda: 0.0)
    events = []
    out = _stream(lambda kind, label, **k: events.append((kind, label, k.get("extra") or {})), stall_at=0.1,
                  chunk_at=0.35)
    assert out["stalled"] is False and out["errored"] is False, out
    host = [e for e in events if e[2].get("kind") == "host_stall"]
    assert len(host) == 1 and host[0][2]["host_stall_s"] == 1.5 and "not blamed" in host[0][1], events
    assert not [e for e in events if "ATASCADO" in e[1]]


def test_a_real_silence_is_still_a_stall(meter, monkeypatch):
    monkeypatch.setattr(ps._fup, "Hold", _Hold)
    monkeypatch.setattr(ps._route, "wait_s", lambda: 0.0)
    events = []
    out = _stream(lambda kind, label, **k: events.append((kind, label)), stall_at=None, chunk_at=0.35)
    assert out["stalled"] is True and any("ATASCADO" in lbl for _, lbl in events)


def test_the_provider_circuit_counts_no_stall_while_the_body_loop_was_stopped(meter, monkeypatch):
    """(b) no streak, no relay: the silence was the host's, never the titular's."""
    monkeypatch.setattr(pc, "_slow_streak", {})
    monkeypatch.setattr(pc, "pick", lambda role=None: {"name": "titular"})
    loop_lag.note(13.0)
    assert pc.note_stall(role=pc.ROLE_VOICE) is None and pc.note_stall(role=pc.ROLE_VOICE) is None
    assert pc._slow_streak == {}, "a stall with the loop stopped must not count against the provider"
    loop_lag._state["stalls"].clear()
    pc.note_stall(role=pc.ROLE_VOICE)
    assert pc._slow_streak == {"titular": 1}, "with the loop running, a stall counts as before"


def test_the_verdict_names_the_host_before_cold_or_pre_token(meter, monkeypatch):
    """(c) a turn whose time went to a stopped loop blames neither the prompt nor the provider — and `note_slow` reads
    it as a cause that breaks the slow streak."""
    m = {"total_ms": 14000, "ttft_ms": 13500, "prompt_tokens": 3000, "tok_per_s": 30, "gap_since_last_s": 200}
    v = tp.verdict({**m, "host_stall_s": 13.2})
    assert v["cause"] == "host" and "HOST PARADO 13.2 s" in v["label"] and v["host_stall_s"] == 13.2
    assert tp.verdict(m)["cause"] == "frio", "without host time the verdict reads as before"
    assert tp.verdict({**m, "gap_since_last_s": 0})["cause"] == "pre_token"
    assert tp.verdict({**m, "host_stall_s": 0.4})["cause"] == "frio", "a stall under HOST_STALL_S names nobody new"
    monkeypatch.setattr(pc, "_slow_streak", {"titular": 1})
    monkeypatch.setattr(pc, "pick", lambda role=None: {"name": "titular"})
    assert pc.note_slow(v, role=pc.ROLE_VOICE) is None and pc._slow_streak == {}


def test_the_close_hands_the_verdict_the_hosts_seconds(meter):
    from nucleo.turn import pipeline_close
    import time
    t_entry = time.time() - 5
    assert pipeline_close._host_stall_s(t_entry) == 0.0
    loop_lag.note(2.0)
    assert pipeline_close._host_stall_s(t_entry) == 2.0
    assert pipeline_close._host_stall_s(time.time() + 1) == 0.0, "a stall that ended before the turn is not its own"
