"""The first turn is ONE system note, never his words (A7, 2026-11-12).

Measured on the operator's own first dialogue, typed: the voice process composed an English
greeting instruction, the admission replaced it with the i18n `kickoff_prompt`, and that text — «introduce yourself
in one line and ask me my name» — was kept in the dialog window and in the short-term buffer as HIS words. On turn
two the model read the order to introduce itself twice (window + «what we were talking about») beside his «pepe»,
and greeted him again. The offer that the greeting should carry (a new name, a male or female voice) was in the text
the admission threw away, so the model never saw it.

Now: one text (`nucleo/turn/kickoff`, the i18n note), recognised by catalog at the gate; the window keeps the
greeting but not the note; the short-term block and the window seed skip the kickoff row's note; the first
prompt's instruction — with the offer — is the introduction phase's block, a system section the kickoff opens.
"""
from __future__ import annotations

import asyncio
import inspect
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from i18n import langs
from memory import db as memdb
from memory import writer as memwriter
from memory._prompt import reads as memreads
from nucleo.turn import kickoff
from nucleo.turn import pipeline_close
from nucleo.turn.prompt import packs as CP
from nucleo.turn.prompt.packs import introduction

ENGINE = Path(__file__).resolve().parents[4]


@pytest.fixture(autouse=True)
def _catalog():
    kickoff._reset_for_tests()
    yield
    kickoff._reset_for_tests()


# ── one text ─────────────────────────────────────────────────────────────────────────────────────────────

def test_the_voice_hands_the_body_the_same_note_the_gate_recognises():
    from voice.engine.pipeline.first_air import greeting_prompt
    for code in ("es", "en"):
        note = greeting_prompt(langs.spec(code))
        assert note == langs.spec(code).kickoff_prompt, code
        assert kickoff.is_kickoff(note), "the gate must read the voice's own first line as the first turn"
    assert langs.spec("es").kickoff_prompt != langs.spec("en").kickoff_prompt, "i18n data, one per language"


@pytest.mark.parametrize("line", ["pepe", "hola", "", "I just connected", "Es el primer turno. Salúdame"])
def test_nothing_he_can_say_is_a_kickoff(line):
    assert not kickoff.is_kickoff(line), line


def test_the_admission_no_longer_substitutes_a_second_text():
    """The substitution at `pipeline_admit` was the second source: with it gone the line the voice sends IS the
    line the model reads, and `history.is_kickoff` reads the same catalog."""
    src = (ENGINE / "nucleo/turn/pipeline_admit.py").read_text(encoding="utf-8")
    assert "kickoff_prompt" not in src
    from memory import history
    assert history.is_kickoff(langs.spec("en").kickoff_prompt) and not history.is_kickoff("pepe")


# ── not his words ────────────────────────────────────────────────────────────────────────────────────────

def _close(first_turn: bool, window: list, operator_text: str) -> None:
    kw = {name: MagicMock() for name in inspect.signature(pipeline_close.close_the_turn).parameters}
    kw.update(acted={"widget": False}, confirm_state={}, clarify={}, timings={}, llm_metrics={},
              _tool_fired=set(), first_turn=first_turn, operator_text=operator_text, spoken_text="Hola, soy Zaelar.",
              text=operator_text)
    for flag in ("data_done", "worker_acted", "style_fired", "deduped", "aside"):
        kw[flag] = {"v": False}
    for req in ("escalate_req", "search_req", "music_req", "images_req", "listing_req", "read_req", "recall_req",
                "reopen_req", "reveal_req"):
        kw[req] = {"v": None}
    for clock in ("t0", "_t_entry", "first_ms", "_acc_ms", "_amap_ms", "_gate_ms"):
        kw[clock] = time.perf_counter()
    kw["brain"]._window = window
    asyncio.run(pipeline_close.close_the_turn(**kw))
    return kw


def test_the_window_keeps_the_greeting_and_not_the_note(monkeypatch):
    """The close is the one door that writes his line into the window (`_dialog.push_user`): on the first turn it is
    not called — the note is not his — and the greeting is appended alone; a normal turn keeps his line."""
    from memory import api as memory
    monkeypatch.setattr(memory, "write", lambda *a, **k: None)
    window: list = []
    kw = _close(True, window, langs.spec("es").kickoff_prompt)
    assert not kw["_dialog"].push_user.called, "the kickoff note was written into the window as his words"
    assert [m["role"] for m in window] == ["assistant"], window
    kw = _close(False, [], "pepe")
    assert kw["_dialog"].push_user.call_args[0][1] == "pepe", "a normal turn keeps his line"


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _conv(u: str, a: str, *, kickoff_row: bool = False) -> int:
    meta = {"source": "conv", "u": u, "a": a, **({"kickoff": True} if kickoff_row else {})}
    return memwriter.insert_memory(f"Operador: {u} · zaelar: {a}", kind="conv", level="short", importance=0.2,
                                   ttl_days=2.0, meta=meta)


def test_the_recent_block_and_the_seed_skip_the_note(fresh_db):
    note = langs.spec("es").kickoff_prompt
    _conv(note, "Hola, soy Zaelar. ¿Cómo te llamas?", kickoff_row=True)
    _conv("pepe", "Encantado, Pepe.")
    texts = [r["text"] for r in memreads.recent_short(limit=10)]
    assert len(texts) == 1 and "pepe" in texts[0], texts
    assert not any(note in t for t in texts), "the kickoff row rode «what we were talking about»"
    seed = memreads.recent_window(limit=6)
    assert [m["role"] for m in seed] == ["assistant", "user", "assistant"], seed
    assert note not in " ".join(m["content"] for m in seed)


# ── the first prompt carries the offer, as a system block ────────────────────────────────────────────────

@pytest.fixture
def phase(monkeypatch):
    store = {"stt_language": "es"}
    monkeypatch.setattr("config.settings.get", lambda k, d=None: store.get(k, d))
    monkeypatch.setattr("config.settings.update", lambda patch: store.update(patch))
    monkeypatch.setattr(introduction, "_known", lambda: {})
    introduction.install()
    return store


@pytest.mark.parametrize("code", ["es", "en"])
def test_the_kickoff_opens_the_phase_block_with_the_offer(phase, code):
    note = langs.spec(code).kickoff_prompt
    composed = CP.compose(note)
    assert composed, "the kickoff is a system note: the phase rides it whatever its length"
    assert "masculina o femenina" in composed and "nombre que quiera" in composed, composed
    assert "PRIMER TURNO" in composed


def test_the_built_first_prompt_carries_the_offer_as_a_system_section(phase, monkeypatch):
    from nucleo.flash import memory_cache
    from nucleo.turn.prompt import builder
    monkeypatch.setattr(memory_cache, "get", lambda: ("", ""))
    system = builder.build_flash_system(turn_text=langs.spec("en").kickoff_prompt)[0]
    assert "masculina o femenina" in system and "CONTEXTO DE FASE" in system
    assert "I just connected" not in system
