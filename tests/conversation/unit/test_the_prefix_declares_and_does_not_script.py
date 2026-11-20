"""The model's prefix declares and does not script (node 13.46, v3.1 B3).

Every line is one of the declared lines (language, input, reads, acts, the orders and their fields) — no sentence of
how to behave; it lists the catalogue's reads; it is byte-identical between turns for the same language and
catalogue (the provider caches it); and it stays under its token ceiling.
"""
from __future__ import annotations

from conversation.ports import ToolSpec
from nucleo.conversation_host import prefix
from nucleo.llm.fast_client import est_tokens

CATALOG = [ToolSpec("search"), ToolSpec("agenda_read"), ToolSpec("about_self")]


def test_every_line_is_a_declared_one():
    text = prefix.build(CATALOG, native="English", name="English")
    assert [line.split(":", 1)[0] for line in text.splitlines()] == list(prefix.LINES)


def test_it_lists_the_reads_of_the_catalogue():
    text = prefix.build(CATALOG, native="español", name="Spanish")
    reads = next(line for line in text.splitlines() if line.startswith("READS:"))
    assert reads == "READS: about_self, agenda_read, search" and "español (Spanish)" in text


def test_it_is_byte_identical_between_turns():
    assert prefix.build(CATALOG, native="English", name="English") == \
        prefix.build(list(reversed(CATALOG)), native="English", name="English")


def test_it_stays_under_its_ceiling_even_with_a_large_catalogue():
    big = [ToolSpec(f"read_{i:02d}") for i in range(40)]
    assert est_tokens(len(prefix.build(big, native="English", name="English"))) <= prefix.MAX_TOKENS


def test_the_current_prefix_reads_the_operators_language(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    assert "LANGUAGE: every reply" in prefix.current(CATALOG)
