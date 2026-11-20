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
    assert reads == "READS: about_self; agenda_read; search" and "español (Spanish)" in text


def test_it_is_byte_identical_between_turns():
    assert prefix.build(CATALOG, native="English", name="English") == \
        prefix.build(list(reversed(CATALOG)), native="English", name="English")


def test_it_stays_under_its_ceiling_with_the_real_catalogue_names_and_held_acts():
    from nucleo.conversation_host import tools_read
    real = prefix.build(tools_read.catalog(), native="English", name="English", agent="Johnny", person="Quinn",
                        held=prefix.held_acts())
    assert est_tokens(len(real)) <= prefix.MAX_TOKENS
    big = [ToolSpec(f"read_{i:02d}", about="w " * 6) for i in range(12)]
    assert est_tokens(len(prefix.build(big, native="English", name="English", held=prefix.held_acts()))) \
        <= prefix.MAX_TOKENS


def test_it_says_who_is_who_what_each_read_is_for_and_what_exists_but_is_held():
    """The smoke's findings (B7b): the agent's name read as the person's vocative, a search refused although offered,
    «tell Rowan…» read as a message FROM Rowan. Declared, never a «don't»: who is who, what each read reaches, and the
    acts that exist and are held in this phase."""
    from nucleo.conversation_host import tools_read
    text = prefix.build(tools_read.catalog(), native="English", name="English", agent="Johnny", person="",
                        held=prefix.held_acts())
    lines = dict(line.split(": ", 1) for line in text.splitlines())
    assert "named Johnny" in lines["YOU"] and "never the person's" in lines["YOU"]
    assert lines["PERSON"] == "name not known yet"
    assert "web_search: the world now" in lines["READS"]
    assert "messaging.send_new" in lines["ACTS"] and "refused" in lines["ACTS"]
    assert "never done, promised or said as done" in lines["ACTS"]          # es-11: «hecho, apuntado» for a held act
    assert "named Quinn" in prefix.build([], native="English", name="English", agent="Johnny", person="Quinn")


def test_the_current_prefix_reads_the_operators_language(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    assert "LANGUAGE: each reply in the language of the person's entries" in prefix.current(CATALOG)
