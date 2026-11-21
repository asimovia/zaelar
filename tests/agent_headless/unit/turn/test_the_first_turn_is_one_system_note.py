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

import time
from pathlib import Path

import pytest

from i18n import langs
from memory import db as memdb
from memory import writer as memwriter
from memory._prompt import reads as memreads

ENGINE = Path(__file__).resolve().parents[4]


# ── one text ─────────────────────────────────────────────────────────────────────────────────────────────

# ── not his words ────────────────────────────────────────────────────────────────────────────────────────

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

# ── his answer to our question reaches the model AS an answer (the turn after the greeting) ──────────────

def test_the_question_is_read_from_the_last_reply_only_while_it_is_the_last_word(fresh_db):
    """The reader the close uses, on the real store: a reply that ended asking frames the next turn; one that ended
    on a statement, or an old one, frames nothing."""
    from nucleo.memory_agent import answer_frame
    _conv("hola", "Hola, soy Zaelar. ¿Cómo te llamas?")
    assert answer_frame.asked_before() == "¿Cómo te llamas?"
    assert answer_frame.asked_before(now=time.time() + 16 * 60) == ""
    _conv("pepe", "Encantado, Pepe.")
    assert answer_frame.asked_before() == ""
