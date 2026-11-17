"""The agent's default name is a per-language catalogue in the genome, and its STT spellings are wake words (V2-929).

The operator, 2026-11-17: the agent is called «Johnny» from the very first moment, in English and in Spanish — chosen
for how it SOUNDS and how a recogniser writes it, not its spelling — and another language may later get its own name
from a small catalogue. So the name is data (`nucleo/genesis.json › persona`), read by one door (`genome/persona.py`):

1. the catalogue decides: `en`/`es` rows, a `*` row for every other language, and a new row renames that language's
   unnamed agents with no code change;
2. the memory never stores the default as a choice: a fresh state reads the catalogue's name, a row an older engine
   stamped with the legacy default reads as unnamed, and a name he gave is kept — even the old default, once chosen;
3. every spelling the STT writes for the name opens the attention gate as the name itself does.
"""
from __future__ import annotations

import json

import pytest

import genome
from genome import persona


@pytest.fixture
def catalogue(tmp_path, monkeypatch):
    """Point the genome at a copy of the shipped genesis; `edit(fn)` rewrites the copy's `persona` section."""
    shipped = json.loads(genome.GENESIS.read_text(encoding="utf-8"))
    f = tmp_path / "genesis.json"

    def edit(fn=lambda p: p):
        data = json.loads(json.dumps(shipped))
        data["persona"] = fn(data["persona"])
        f.write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setitem(genome._cache, "data", None)
        monkeypatch.setattr(persona, "_memo", {"mtime": None, "persona": {}})
    monkeypatch.setattr(genome, "GENESIS", f)
    edit()
    return edit


# ── 1 · the catalogue decides ─────────────────────────────────────────────────────────────────────────────

def test_the_shipped_catalogue_names_it_johnny_in_english_spanish_and_every_other_language():
    assert persona.default_name("en") == persona.default_name("es-419") == "Johnny"
    assert persona.default_name("fr") == "Johnny", "a language with no row falls back to the `*` row"


def test_a_language_gets_its_own_name_by_a_row_of_data(catalogue):
    catalogue(lambda p: {**p, "name": {**p["name"], "fr": "Jeannot"}})
    assert persona.default_name("fr") == "Jeannot"
    assert persona.default_name("es") == "Johnny"


def test_the_engine_code_names_no_default_of_its_own(catalogue):
    """The disarm of the catalogue: a `*` row changed is what every unnamed agent goes by."""
    catalogue(lambda p: {**p, "name": {"*": "Nemo"}})
    assert persona.default_name("es") == persona.default_name("en") == "Nemo"


# ── 2 · the memory never stores the default as a choice ───────────────────────────────────────────────────

def test_a_new_account_reads_the_catalogue_and_never_stores_it(mem):
    from memory import state
    assert state.read()["assistant_name"] == "Johnny"
    state.patch({"location": "Soria"})                       # any write: the default must not be stamped
    row = json.loads(mem.query_one("SELECT data FROM state WHERE id=1")["data"])
    assert row["assistant_name"] is None, "the default was stamped as if he had chosen it"


def test_the_legacy_default_an_older_engine_stamped_reads_as_unnamed(mem):
    from memory import state
    mem.execute("INSERT INTO state (id, data) VALUES (1, ?)",
                (json.dumps({"assistant_name": "Zaelar", "language": "es"}),))
    assert state.read()["assistant_name"] == "Johnny"


def test_a_name_he_gave_is_kept_even_the_old_default_once_chosen(mem):
    from memory import state
    state.patch({"assistant_name": "Lola"})
    assert state.read()["assistant_name"] == "Lola"
    state.patch({"assistant_name": "Zaelar"})                 # chosen AFTER the catalogue: a real choice
    assert state.read()["assistant_name"] == "Zaelar"


# ── 3 · every spelling the STT writes for the name is a wake word ─────────────────────────────────────────

@pytest.fixture
def unnamed(monkeypatch):
    from voice import attention
    monkeypatch.setattr(attention, "_state", {**attention._state, "assistant_name": ""})
    monkeypatch.delenv("ZAELAR_WAKEWORDS", raising=False)
    monkeypatch.setenv("ZAELAR_ATTENTION", "wakeword")       # word activation on: only the name opens the gate
    return attention


@pytest.mark.parametrize("heard", ["Johnny, pon música", "Jonny, play some music", "oye Yoni, ¿qué tiempo hace?",
                                   "Hey Johnnie what's on today"])
def test_the_default_name_opens_the_gate_however_the_stt_spells_it(unnamed, heard):
    assert unnamed.has_wakeword(heard), heard
    assert unnamed.evaluate(heard).reason == "wakeword"


def test_a_spelling_is_a_wake_word_only_while_that_is_the_name(unnamed):
    unnamed.set_assistant_name("Lola")
    assert unnamed.has_wakeword("Lola, pon música") and not unnamed.has_wakeword("Yoni, pon música")
    assert unnamed.has_wakeword("zaelar, pon música"), "the product's name keeps working after a rename"


def test_the_spellings_are_data_of_the_name(catalogue, unnamed):
    catalogue(lambda p: {**p, "heard_as": {}})
    assert not unnamed.has_wakeword("Yoni, pon música"), "a spelling answered with no row declaring it"
    assert unnamed.has_wakeword("Johnny, pon música")


def test_the_browser_ear_gets_the_same_spellings():
    from config import settings
    table = persona.wake_table()
    assert "yoni" in table["johnny"] and "jonny" in table["johnny"]
    import inspect
    assert "wake_names" in inspect.getsource(settings), "GET /api/settings no longer serves the spellings"
