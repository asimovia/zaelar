"""Tests for the voice prompt builder, nucleo/turn/prompt/ (V2-004 · T67) — the FlashBrain prompt composes its own MEMORY (state+query)."""
import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from nucleo.flash import recall_heuristics as _rh
from memory import state_cache as memory_cache
from nucleo.turn.prompt import builder as prompt


from nucleo import done_lines as live_record
@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    memory_cache.reset()   # the session cache (T114) is global; start clean for each test
    yield
    memory_cache.reset()
    memdb.reset_db()


@pytest.mark.parametrize("text", [
    "where is my car",
    "where's my car?",
    "¿dónde está mi coche?",
    "do you remember what I told you?",
    "¿te acuerdas de mi cita del dentista?",
    "what did I tell you about the meeting",
    "recuérdame qué dije de la reunión",   # 'what I said about'
])
def test_needs_recall_true(text):
    assert _rh.needs_recall(text) is True


@pytest.mark.parametrize("text", [
    "hola, buenos días",
    "¿qué tal estás?",
    "let's talk about my weekend plans",
    "show me the clock please",
    "cuéntame un chiste",
    "¿me pones el tiempo en pantalla?",
])
def test_needs_recall_false(text):
    assert _rh.needs_recall(text) is False


# ── proactivity and multi-intent (use cases from 2026-08-18) ─────────────────────────────────────────
def test_the_cron_line_makes_a_spoken_reminder_insufficient():
    """V2-121 · `remember-and-remind-deadline`. Saying «I'll remind you» does not schedule anything; the prompt has to
    say it explicitly, because the run measured three turns claiming it was scheduled with zero
    mechanism behind it."""
    line = live_record._cron_line()
    assert "[[cron.create]]" in line
    assert "EN ESE TURNO" in line
    assert "YYYY-MM-DD HH:MM" in line       # the format that makes a one-time reminder EXPRESSIBLE
    assert "add_meeting" in line            # noting it down and reminding are two different things, and both are requested


# test_the_background_task_list_states_what_it_is_NOT_for: retired by V2-878 §2 — it asserted an instruction of the running-errands block, which is facts only now.


# test_the_prompt_forbids_answering_a_concrete_question_with_process: retired by V2-878 §2 — it asserted an instruction of the running-errands block, which is facts only now.
