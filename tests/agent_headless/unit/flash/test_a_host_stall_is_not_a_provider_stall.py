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
    monkeypatch.setattr(loop_lag, "_say", lambda s, who="host": None)
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


def _stream(emit, stall_at: float | None, chunk_at: float, quiet_ms: int = 200, block_s: float = 0.0) -> dict:
    """One turn whose only chunk arrives at `chunk_at`; a host stall of 1.5 s is noted at `stall_at`."""
    buf: list[str] = []

    class FC:
        def stream(self, messages, spec=None, tools=None, on_tool_call=None, metrics=None):
            async def gen():
                await asyncio.sleep(chunk_at)
                yield "hola"
            return gen()

    async def run():
        if stall_at is not None:     # the loop really held 0.3 s, then the probe's reading of it
            import time
            asyncio.get_running_loop().call_later(stall_at, lambda: (time.sleep(0.3), loop_lag.note(0.3, faults=1)))
        if block_s:     # a block that ENDS 10 ms into the wait: almost all of it before
            asyncio.get_running_loop().call_later(0.01, lambda: loop_lag.note(block_s))
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
    from nucleo.workers import envelope
    monkeypatch.setattr(envelope, "policy", lambda: {**envelope._DEFAULTS, "loop_lag_s": 0.1})
    events = []
    out = _stream(lambda kind, label, **k: events.append((kind, label, k.get("extra") or {})), stall_at=0.1,
                  chunk_at=0.45)
    assert out["stalled"] is False and out["errored"] is False, out
    host = [e for e in events if e[2].get("kind") == "host_stall"]
    assert len(host) == 1 and 0.25 <= host[0][2]["host_stall_s"] <= 0.3 and "not blamed" in host[0][1], events
    assert not [e for e in events if "ATASCADO" in e[1]]


def test_a_real_silence_is_still_a_stall(meter, monkeypatch):
    monkeypatch.setattr(ps._fup, "Hold", _Hold)
    monkeypatch.setattr(ps._route, "wait_s", lambda: 0.0)
    events = []
    out = _stream(lambda kind, label, **k: events.append((kind, label)), stall_at=None, chunk_at=0.35)
    assert out["stalled"] is True and any("ATASCADO" in lbl for _, lbl in events)


def test_a_loop_that_keeps_stalling_does_not_hold_a_dead_provider_forever(meter, monkeypatch):
    """(b) P2: every stall used to restart the deadline whole — with the loop stalling every few hundred ms over a
    provider that never answers, the turn waited for ever. Only the stopped seconds are given back: the silence
    measured while the loop RAN still reaches the deadline."""
    monkeypatch.setattr(ps._fup, "Hold", _Hold)
    monkeypatch.setattr(ps._route, "wait_s", lambda: 0.0)
    from nucleo.workers import envelope
    monkeypatch.setattr(envelope, "policy", lambda: {**envelope._DEFAULTS, "loop_lag_s": 0.01})
    events = []

    async def hiccups():
        while True:
            await asyncio.sleep(0.1)
            loop_lag.note(0.04)

    real_run = asyncio.run

    def run_with_hiccups(coro):
        async def both():
            h = asyncio.ensure_future(hiccups())
            try:
                return await coro
            finally:
                h.cancel()
        return real_run(both())
    monkeypatch.setattr(asyncio, "run", run_with_hiccups)
    out = _stream(lambda kind, label, **k: events.append((kind, label)), stall_at=None, chunk_at=3.0)
    assert out["stalled"] is True, "a dead provider under a stalling loop was never cut (its chunk came at 3 s)"


def test_a_block_that_ended_as_the_wait_began_gives_the_deadline_nothing_back(meter, monkeypatch):
    """(b2) E3 audit: a 30 s block just BEFORE the wait counted whole — the dead provider was cut ~21 s later. Only
    the stall's overlap with the wait is handed back."""
    monkeypatch.setattr(ps._fup, "Hold", _Hold)
    monkeypatch.setattr(ps._route, "wait_s", lambda: 0.0)
    out = _stream(lambda kind, label, **k: None, stall_at=None, chunk_at=3.0, block_s=30.0)
    assert out["stalled"] is True, "a block that ended as the wait began was handed back whole"
    import time
    loop_lag._state["stalls"].clear()
    now = time.monotonic()
    loop_lag.note(30.0, mono=now)
    assert loop_lag.stalled_since(mono=now - 0.5) == 0.5 and loop_lag.stalled_since(mono=now - 40) == 30.0


def test_the_provider_circuit_counts_a_stall_whose_loop_seconds_were_already_taken_out(meter, monkeypatch):
    """(c) a stall that reaches the circuit is net of the loop's stopped seconds, so it counts even when the loop
    hiccuped within the last minute (P2: one hiccup used to switch the relay off for 60 s)."""
    monkeypatch.setattr(pc, "_slow_streak", {})
    monkeypatch.setattr(pc, "pick", lambda role=None: {"name": "titular"})
    loop_lag.note(13.0)
    pc.note_stall(role=pc.ROLE_VOICE)
    assert pc._slow_streak == {"titular": 1}


def test_the_verdict_names_the_host_before_cold_or_pre_token(meter, monkeypatch):
    """(d) a turn whose time went to a stopped loop blames neither the prompt nor the provider — and `note_slow` reads
    it as a cause that breaks the slow streak."""
    m = {"total_ms": 14000, "ttft_ms": 13500, "prompt_tokens": 3000, "tok_per_s": 30, "gap_since_last_s": 200}
    v = tp.verdict({**m, "host_stall_s": 13.2})
    assert v["cause"] == "host" and "HOST STALLED 13.2 s" in v["label"] and v["host_stall_s"] == 13.2
    assert tp.verdict(m)["cause"] == "frio", "without host time the verdict reads as before"
    assert tp.verdict({**m, "gap_since_last_s": 0})["cause"] == "pre_token"
    assert tp.verdict({**m, "host_stall_s": 0.4})["cause"] == "frio", "a stall under HOST_STALL_S names nobody new"
    own = tp.verdict({**m, "own_stall_s": 13.2})
    assert own["cause"] == "own_stall" and "HOST" not in own["label"], "our own block was named the host's"
    unknown = tp.verdict({**m, "unknown_stall_s": 13.0})          # Fly's stolen CPU, macOS's compressor: unattributed
    assert unknown["cause"] == "loop_stall" and "HOST" not in unknown["label"], unknown
    monkeypatch.setattr(pc, "_slow_streak", {"titular": 1})
    monkeypatch.setattr(pc, "pick", lambda role=None: {"name": "titular"})
    assert pc.note_slow(unknown, role=pc.ROLE_VOICE) is None and pc._slow_streak == {}, \
        "an unattributed loop stall counted as the provider's slowness (E3 audit P1)"
    monkeypatch.setattr(pc, "_slow_streak", {"titular": 1})
    monkeypatch.setattr(pc, "pick", lambda role=None: {"name": "titular"})
    assert pc.note_slow(v, role=pc.ROLE_VOICE) is None and pc._slow_streak == {}


def test_the_close_hands_the_verdict_the_hosts_seconds(meter):
    from nucleo.turn import pipeline_close
    import time
    t_entry = time.time() - 5
    assert pipeline_close._host_stall_s(t_entry)["host_stall_s"] == 0.0
    loop_lag.note(2.0, faults=1)
    loop_lag.note(3.0, cpu_s=3.0)
    assert pipeline_close._host_stall_s(t_entry) == {"host_stall_s": 2.0, "own_stall_s": 3.0,
                                                      "unknown_stall_s": 0.0}, "one origin each"
    assert pipeline_close._host_stall_s(time.time() + 1)["host_stall_s"] == 0.0, "a stall that ended before the turn is not its own"
