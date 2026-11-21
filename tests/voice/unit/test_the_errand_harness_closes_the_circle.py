from tests import voice_turn_source as _vts
"""V2-660 — the errand HARNESS closes the circle, and the window measures silence from speech ONSET.

Session 0141a72a (2026-09-11), two defects in one minute:
  1. «Johnny.» opened a 5 s window; he began «Enséñame la declaración de independencia» 2 s later and the
     STT finalized it 6 s later — judged at the END it fell outside the window and became room noise.
  2. After his «Adelante» the model said «Claro, aquí tienes el texto completo…» having run ONE web_search;
     the `documento` card was open and EMPTY, and nothing compared the claim with the screen.
"""
import asyncio
import os

import pytest

from nucleo.circuit import harness
from voice import attention

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for k in ("ZAELAR_ATTENTION", "ZAELAR_ATTENTION_WINDOW", "ZAELAR_WAKEWORDS"):
        monkeypatch.delenv(k, raising=False)
    attention.reset()
    harness.reset()
    yield
    attention.reset()
    harness.reset()


def _src(rel: str) -> str:
    return _vts.read(os.path.join(ENG, rel))


# ── the window measures SILENCE, and silence ends at speech onset ───────────────────────────────────────
def test_a_sentence_begun_inside_the_window_is_directed_even_if_it_ends_after_it(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    t = 1000.0
    attention.note_directed(now=t)              # «Johnny.»
    attention.note_speech_onset(now=t + 2)      # he starts the sentence
    v = attention.evaluate("enséñame la declaración de independencia", now=t + 6)   # STT final, 6 s later
    assert v.directed and v.reason == "active_window"


def test_without_an_onset_the_end_of_speech_still_rules(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    t = 1000.0
    attention.note_directed(now=t)
    assert not attention.evaluate("enséñame la declaración", now=t + 6).directed


def test_a_stale_onset_from_before_the_anchor_grants_nothing(monkeypatch):
    """An onset OLDER than the anchor belongs to earlier speech — it must not stretch the window."""
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    t = 1000.0
    attention.note_speech_onset(now=t - 30)
    attention.note_speech_end(now=t - 28)       # V2-661: that earlier speech ENDED — it is not the anchor's utterance
    attention.note_directed(now=t)
    assert not attention.evaluate("y otra cosa", now=t + 6).directed


# ── the ledger and the verifier ─────────────────────────────────────────────────────────────────────────
def _fake_view(monkeypatch, views: dict, opened: set | None = None):
    from nucleo.circuit import verify
    monkeypatch.setattr(verify, "card_view", lambda wid: views.get(wid))
    monkeypatch.setattr(verify, "card_on_screen", lambda wid: (wid in opened) if opened is not None else None)
