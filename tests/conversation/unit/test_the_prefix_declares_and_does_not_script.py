"""The model's prefix declares and does not script (node 13.46, v3.1 B3).

Every line is one of the declared lines (language, input, reads, acts, the orders and their fields) — no sentence of
how to behave; it lists the catalogue's reads; it is byte-identical between turns for the same language and
catalogue (the provider caches it); and it stays under its token ceiling.
"""
from __future__ import annotations

from conversation.ports import ToolSpec
from conversation.types import EffectClass
from nucleo.conversation_host import acts, prefix
from nucleo.llm.fast_client import est_tokens

CATALOG = [ToolSpec(n, effect_class=EffectClass.READ) for n in ("search", "agenda_read", "about_self")]


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
    from i18n import langs
    real_catalog = acts.HostTools().catalog()
    for code in ("en", "es"):
        real = prefix.build(real_catalog, native="English", name="English", agent="Johnny", person="Quinn",
                            held=prefix.held_acts(real_catalog), budget={"voice": "two short sentences", "text": "a short paragraph"},
                            style=langs.words("speech_style", code))
        assert est_tokens(len(real)) <= prefix.MAX_TOKENS, code
    big = [ToolSpec(f"read_{i:02d}", about="w " * 6, effect_class=EffectClass.READ) for i in range(12)]
    assert est_tokens(len(prefix.build(big, native="English", name="English", held=prefix.held_acts()))) \
        <= prefix.MAX_TOKENS


def test_it_says_who_is_who_what_each_read_is_for_and_what_exists_but_is_held():
    """The smoke's findings (B7b): the agent's name read as the person's vocative, a search refused although offered,
    «tell Rowan…» read as a message FROM Rowan. Declared, never a «don't»: who is who, what each read reaches, and the
    acts that exist and are held in this phase."""
    catalog = acts.HostTools().catalog()
    text = prefix.build(catalog, native="English", name="English", agent="Johnny", person="",
                        held=prefix.held_acts(catalog))
    lines = dict(line.split(": ", 1) for line in text.splitlines())
    assert "named Johnny" in lines["YOU"] and "never the person's" in lines["YOU"]
    assert "in the first person" in lines["YOU"]                             # U27-es-011: «Johnny no puede…»
    assert lines["PERSON"] == "name not known yet"
    assert "web_search: the world now" in lines["READS"]
    assert "show_widget" not in lines["READS"]                                # an act is never listed as a read
    assert "show_widget" not in lines["ACTS"]                                 # F2 step 1: a local act is no held one
    assert "errand.start" not in lines["ACTS"] and "errand.moves_money" in lines["ACTS"]   # what start_task covers
    assert "messaging.autorespond" in lines["ACTS"] and "refused" in lines["ACTS"]
    assert "messaging.send_new" not in lines["ACTS"]                         # step 4: send_message covers it
    assert "never done, promised or said as done" in lines["ACTS"]          # es-11: «hecho, apuntado» for a held act
    assert "named Quinn" in prefix.build([], native="English", name="English", agent="Johnny", person="Quinn")


def test_the_current_prefix_reads_the_operators_language(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    assert "LANGUAGE: each reply in the language of the person's entries" in prefix.current(CATALOG)


def test_the_style_line_is_the_language_packs_own(monkeypatch):
    """How the agent speaks (short, like a person, never reading back a number or a message's text) is the language
    pack's `speech_style` — DNA the genome owns and a generated language translates — never a sentence of the host."""
    import inspect

    from i18n import langs
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")
    style = langs.words("speech_style", "es")
    assert style and style != langs.words("speech_style", "en")
    lines = dict(line.split(": ", 1) for line in prefix.current(CATALOG).splitlines())
    assert lines["STYLE"] == style
    assert style[:30] not in inspect.getsource(prefix)


def test_the_stop_wording_is_declared_data():
    """E-2: «te paso la tarea dos» chose `stop_voice`. When a stop is chosen is the declared `stop_rule` and each stop's
    own description, both in `declared.json` — the ORDERS line and the tool list carry them verbatim."""
    from nucleo.conversation_host import model
    from nucleo.conversation_host.declared import declared
    d = declared()
    orders = next(line for line in prefix.build([], native="English", name="English").splitlines()
                  if line.startswith("ORDERS:"))
    assert d["stop_rule"] in orders
    told = {t["function"]["name"]: t["function"].get("description") for t in model.tools_for([])}
    assert {n: told[n] for n in d["stops"]} == d["stops"]
