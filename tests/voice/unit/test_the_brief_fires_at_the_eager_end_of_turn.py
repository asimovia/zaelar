"""The turn's brief fires when the ear ANNOUNCES the end of turn, not when it confirms it (V2-863, 2026-11-08).

Deepgram Flux emits an eager end of turn before the confirmed one; the LiveKit plugin forwards it as a
`PREFLIGHT_TRANSCRIPT`. Fired there, the one Jev call of the turn (250 ms p50) has landed by the time the turn is
armed, so the cover is decided from the verdict and not from a regex. The eager brief is kept by the sentence AS
SAID — the eager transcript and the confirmed one differ by a full stop and a capital — and a sentence that grew
(he resumed) is a different sentence with its own brief.
"""
from __future__ import annotations

import asyncio
import threading
import time

import pytest
from livekit.agents import stt as lk_stt

from nucleo.turn import brief_turn as bt
from voice.engine.pipeline import eager_brief as eb


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    bt._PREFIRED.clear()
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: None)
    yield
    bt._PREFIRED.clear()


def _handle() -> dict:
    return {"event": threading.Event(), "result": None}


def _ev(kind, text: str):
    return lk_stt.SpeechEvent(type=kind, alternatives=[lk_stt.SpeechData(language="es", text=text)])


# ── the wrapper: one eager event → one brief; every event passes through untouched ─────────────────────────

def _run(events, asked: list):
    async def default_impl(agent, audio, model_settings):
        for ev in events:
            yield ev

    async def go():
        out = []
        async for ev in eb.stt_node_firing_the_brief(None, default_impl, None, None):
            out.append(ev)
        return out
    return asyncio.run(go())


def test_a_preflight_transcript_fires_the_brief_once_and_every_event_passes_through(monkeypatch):
    asked: list = []
    monkeypatch.setattr("nucleo.turn.brief.ask_for_turn", lambda text, **kw: asked.append(text) or _handle())
    events = [_ev(lk_stt.SpeechEventType.INTERIM_TRANSCRIPT, "que tiempo"),
              _ev(lk_stt.SpeechEventType.PREFLIGHT_TRANSCRIPT, "que tiempo hace en madrid"),
              _ev(lk_stt.SpeechEventType.FINAL_TRANSCRIPT, "¿Qué tiempo hace en Madrid?")]
    out = _run(events, asked)
    assert asked == ["que tiempo hace en madrid"], "the brief fires on the eager event, once"
    assert [id(e) for e in out] == [id(e) for e in events], "the same event objects, in order, none dropped"


def test_an_interim_transcript_fires_nothing(monkeypatch):
    asked: list = []
    monkeypatch.setattr("nucleo.turn.brief.ask_for_turn", lambda text, **kw: asked.append(text) or _handle())
    _run([_ev(lk_stt.SpeechEventType.INTERIM_TRANSCRIPT, "que tiempo hace")], asked)
    assert asked == []


def test_the_same_eager_sentence_twice_is_one_brief(monkeypatch):
    asked: list = []
    monkeypatch.setattr("nucleo.turn.brief.ask_for_turn", lambda text, **kw: asked.append(text) or _handle())
    h1 = bt.fire_early("que tiempo hace en madrid")
    h2 = bt.fire_early("Que tiempo hace en Madrid")
    assert h1 is h2 and asked == ["que tiempo hace en madrid"]


# ── the hand-over: the turn that admits the SAME words reuses the early brief ──────────────────────────────

def test_the_admitted_turn_finds_the_brief_fired_for_the_same_words_as_said(monkeypatch):
    h = _handle()
    monkeypatch.setattr("nucleo.turn.brief.ask_for_turn", lambda text, **kw: h)
    assert bt.fire_early("que tiempo hace en madrid") is h
    assert bt.prefired("¿Qué tiempo hace en Madrid?") is h, "case, accents and punctuation are the transcriber's"
    assert bt.prefired("¿Qué tiempo hace en Madrid?") is None, "handed over once"


def test_different_words_do_not_get_someone_elses_brief(monkeypatch):
    h = _handle()
    monkeypatch.setattr("nucleo.turn.brief.ask_for_turn", lambda text, **kw: h)
    bt.fire_early("que tiempo hace en madrid")
    assert bt.prefired("que tiempo hace en madrid mañana") is None, "he resumed: a new sentence, a new brief"
    assert bt.prefired("que tiempo hace en madrid") is h, "…and the original is still there for its own turn"


def test_a_stale_early_brief_is_not_handed_over():
    h = _handle()
    bt._PREFIRED[bt._key("que tiempo hace")] = (time.time() - bt.PREFIRED_TTL_S - 1, h)
    assert bt.prefired("que tiempo hace") is None


def test_two_sentences_in_flight_coexist(monkeypatch):
    handles = {}
    monkeypatch.setattr("nucleo.turn.brief.ask_for_turn", lambda text, **kw: handles.setdefault(text, _handle()))
    bt.fire_early("que tiempo hace")
    bt.fire_early("pon música")
    assert bt.prefired("¿Qué tiempo hace?") is handles["que tiempo hace"]
    assert bt.prefired("Pon música.") is handles["pon música"]


def test_the_early_briefs_are_bounded():
    for i in range(bt._PREFIRED_MAX + 3):
        bt._remember_prefired(f"frase {i}", _handle())
    assert len(bt._PREFIRED) == bt._PREFIRED_MAX
    assert bt.prefired("frase 0") is None, "the oldest aged out first"
