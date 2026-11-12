"""V2-888 — a pause that was a start is not a turn.

Measured 2026-11-11 (cloud session, Flux ear): «A ver…» [1.7 s] «ponme un videoclip de X». The end of turn committed
«Aversiones.», he resumed 0.1 s later and the turn answered «No te he entendido eso». LiveKit cut that speech when his
voice came back, but the reply entered the dialogue window and the next turn read a misunderstanding that never
happened. With Flux each segment is its own turn, so the prefix guard (`_extends`) never fires: the structural signal
is HIS VOICE resuming after the reply began (`nucleo.input.typed.resumed_since`), as long as voice that would
interrupt a reply — a cough is not a sentence going on.
"""
import asyncio
import inspect
import time
from unittest.mock import MagicMock

import pytest

from nucleo.input import typed


@pytest.fixture(autouse=True)
def _clean_voice_state():
    typed.reset()
    yield
    typed.reset()


def _voice(onset: float, end: float | None) -> None:
    typed.note_onset(onset)
    if end is not None:
        typed.note_end(end)


# ── 1. The signal ───────────────────────────────────────────────────────────────────────────────────────────────

def test_voice_resumed_after_the_reply_began_supersedes_it():
    _voice(10.1, 11.0)                                   # 0.9 s of voice, after a reply begun at 10.0
    assert typed.resumed_since(10.0, now=11.2) is True


def test_voice_still_going_counts_while_it_lasts():
    _voice(10.1, None)
    assert typed.resumed_since(10.0, now=10.5) is False  # 0.4 s so far: not yet a sentence going on
    assert typed.resumed_since(10.0, now=10.8) is True


def test_a_cough_is_not_a_sentence_going_on():
    _voice(10.1, 10.3)                                   # 0.2 s
    assert typed.resumed_since(10.0, now=12.0) is False


def test_voice_from_before_the_reply_began_is_the_sentence_itself():
    _voice(8.0, 9.8)
    assert typed.resumed_since(10.0, now=12.0) is False


def test_a_turn_with_no_mark_is_never_superseded_by_the_microphone():
    _voice(10.1, 11.0)                                   # a typed turn: no reply mark
    assert typed.resumed_since(None, now=12.0) is False


# ── 2. The stream reads it (Flux: each segment is a turn of its own, no prefix growth) ──────────────────────────

class _Stream:
    def __init__(self, text: str, mark: float | None):
        from types import SimpleNamespace
        from voice.engine.llm.providers.nucleo import NucleoLLMStream
        self._llm = SimpleNamespace(_utterance={"text": text, "at": 0.0})
        self._turn_text = text
        self._resume_mark = mark
        self._superseded = NucleoLLMStream._superseded.__get__(self)


def test_a_flux_segment_he_went_on_from_is_superseded():
    now = time.monotonic()
    _voice(now - 1.0, now - 0.2)                         # he resumed after the reply began, 0.8 s of voice
    assert _Stream("Aversiones.", now - 1.1)._superseded() is True


def test_a_flux_segment_with_silence_after_it_is_answered():
    now = time.monotonic()
    _voice(now - 3.0, now - 1.5)                         # his own sentence, before the reply began
    assert _Stream("Ponme un videoclip de Shakira.", now - 1.2)._superseded() is False


# ── 3. The close: his words stay, a reply to a sentence he went on with does not ────────────────────────────────

def _close(superseded, *, acted: bool):
    from nucleo.turn import pipeline_close
    kw = {name: MagicMock() for name in inspect.signature(pipeline_close.close_the_turn).parameters}
    kw.update(acted={"widget": False}, confirm_state={}, clarify={}, timings={}, llm_metrics={},
              _tool_fired=set(), first_turn=False, operator_text="Aversiones.", text="Aversiones.",
              spoken_text="No te he entendido eso.", _superseded=superseded)
    for flag in ("data_done", "worker_acted", "style_fired", "deduped", "aside"):
        kw[flag] = {"v": False}
    for req in ("escalate_req", "search_req", "music_req", "images_req", "listing_req", "read_req", "recall_req",
                "reopen_req", "reveal_req"):
        kw[req] = {"v": None}
    for clock in ("t0", "_t_entry", "first_ms", "_acc_ms", "_amap_ms", "_gate_ms"):
        kw[clock] = time.perf_counter()
    kw["motor"]._ht.turn_handled.return_value = acted
    kw["motor"]._WINDOW_MAX = 12
    kw["_dialog"] = __import__("nucleo.flash.dialog", fromlist=["x"])
    brain = kw["brain"]
    brain._window = []
    brain._acc = None
    brain._judged_turn = None
    asyncio.run(pipeline_close.close_the_turn(**kw))
    return brain


@pytest.fixture
def _no_memory(monkeypatch):
    from memory import api as memory
    monkeypatch.setattr(memory, "write", lambda *a, **k: None)


def test_a_superseded_reply_stays_out_of_the_window_and_his_words_are_owed(_no_memory):
    brain = _close(lambda: True, acted=False)
    roles = [m.get("role") for m in brain._window]
    assert roles == ["user"], brain._window
    assert brain._cut_unanswered[0] == "Aversiones."


def test_a_reply_that_was_not_superseded_enters_the_window(_no_memory):
    brain = _close(lambda: False, acted=False)
    assert [m.get("role") for m in brain._window] == ["user", "assistant"]


def test_a_superseded_turn_that_acted_keeps_its_reply(_no_memory):
    brain = _close(lambda: True, acted=True)
    assert [m.get("role") for m in brain._window] == ["user", "assistant"]


def test_the_turn_hands_its_superseded_check_to_the_close():
    """The close only reads what the pipeline hands it: without this seam the window guard is inert, silently."""
    from nucleo.turn import pipeline, pipeline_close
    assert "_superseded" in inspect.signature(pipeline_close.close_the_turn).parameters
    assert '"_superseded": self._superseded' in inspect.getsource(pipeline.run)


# ── 4. A superseded turn that ACTED is counted, never undone (group A step 6: measure before deciding) ───────────

def _unheard(superseded, *, acted: bool, act_at: float | None, resumed_at: float):
    from types import SimpleNamespace
    from nucleo.turn import resume_cut
    brain = SimpleNamespace(_turn_calls=[{"name": "widget_data", "args": {"widget": "music", "action": "set_volume"}}])
    if act_at is not None:
        resume_cut.note_act(brain, now=act_at)
    _voice(resumed_at, resumed_at + 0.8)
    events = []
    out = resume_cut.reply_unheard(superseded, acted, brain=brain, text="en el año", spoken_text="Volumen al 69.",
                                   emit=lambda *a, **k: events.append((a, k)))
    return out, [k for a, k in events if "superado que actuó" in a[1]]


def test_a_superseded_turn_that_acted_is_counted_with_its_act_and_the_gap():
    out, acted = _unheard(lambda: True, acted=True, act_at=100.0, resumed_at=100.25)
    assert out is False                                  # the reply stays: nothing is undone
    assert len(acted) == 1, acted
    extra = acted[0]["extra"]
    assert extra["acts"] == ["music:set_volume"] and extra["fragment"] == "en el año"
    assert extra["act_to_resume_ms"] == 250 and "trace_id" in extra


def test_a_superseded_turn_that_did_nothing_is_not_counted_as_acting():
    out, acted = _unheard(lambda: True, acted=False, act_at=None, resumed_at=100.25)
    assert out is True and acted == []


def test_a_turn_that_acted_and_was_not_superseded_is_not_counted():
    out, acted = _unheard(lambda: False, acted=True, act_at=100.0, resumed_at=100.25)
    assert out is False and acted == []


def test_the_executor_times_the_act_for_the_count():
    from nucleo.flash import tool_executor_calls
    assert "_resume_cut.note_act(brain)" in inspect.getsource(tool_executor_calls._on_tool_call)
