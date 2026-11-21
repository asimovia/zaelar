"""V2-668 · a QUESTION about what a widget holds is answered by READING that widget — `read_widget`.

Measured live, session 53de97d4 (2026-09-11, 10:58:33 → 11:00:03): «¿a qué hora tengo la cita con Hacienda?»
was answered «no la tengo con hora» while the agenda held `11:30–12:30 · Cita Agencia Tributaria` in one
line. Six turns later, after the operator opened the card BY HAND, the model said «hoy a las once y media» —
calling no tool: a widget's interior only ever reached the prompt while the card was OPEN, and no tool could
read a closed one. `widget_data` executes, `recall` remembers his life, `web_search` reads the world; nothing
read what his own widget stores.
"""
from __future__ import annotations

from tests import voice_turn_source as _vts

import re
import time

import pytest


# ── the door exists, is never trimmed, and routes ─────────────────────────────────────────────────────────

from widgets import read as widget_read
# ── resolution: names only, never «the card that is open» ────────────────────────────────────────────────
def test_resolve_keeps_an_instance_of_a_catalog_widget():
    """Demo sandbox 2026-11-05, S1: «so how did the monitors go, show me» read `results::d88d50-1` — the errand's
    sheet — and `resolve` narrowed it to the base `results`: the EMPTY base sheet was read and shown beside it, and
    S3 «open the best deal» landed on the empty one. An instance of a catalogue widget is read as itself."""
    assert widget_read.resolve("results::d88d50-1") == "results::d88d50-1"
    assert widget_read.resolve("results::d88d50-1", "so how did the monitors go, show me") == "results::d88d50-1"
    assert widget_read.resolve("nothing-such::1") is None


def test_resolve_takes_the_exact_id_or_the_name_the_sentence_carries():
    assert widget_read.resolve("agenda") == "agenda"
    assert widget_read.resolve("la agenda", "¿a qué hora tengo la cita con Hacienda?") == "agenda"
    assert widget_read.resolve("", "abre la agenda y dime qué tengo") == "agenda"
    # (a sentence naming TWO widgets — «la agenda y dime la hora» — resolves to the stronger alias, the clock;
    #  that is the resolver working, not this door: the model names the widget it means in `widget_id`.)


def test_resolve_names_nothing_when_nothing_is_named(monkeypatch):
    """The Hacienda sentence names no widget by alias — resolution is honest about it, and never falls back to
    whatever card is open (V2-666's rule, applied to reading)."""
    from memory import api as _memapi
    monkeypatch.setattr(_memapi, "state", lambda: {"open_widgets": ["youtube"], "recent_widgets": []})
    assert widget_read.resolve("", "¿a qué hora tengo la cita con Hacienda?") is None
    assert widget_read.resolve("hacienda", "¿a qué hora tengo la cita con Hacienda?") is None


# ── the read: the agenda's hour, with the card CLOSED ─────────────────────────────────────────────────────
@pytest.fixture
def _isolated_agenda(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    from nucleo.pulse import scheduler
    monkeypatch.setattr(scheduler, "create", lambda prompt, stamp, name="": {"ok": True, "id": "job1"})
    monkeypatch.setattr(scheduler, "cancel", lambda ref: None)
    from widgets.agenda import data as agenda
    today = time.strftime("%Y-%m-%d")
    r = agenda.apply_action("add_meeting", {"title": "Cita Agencia Tributaria - certificado de persona jurídica",
                                            "date": today, "startTime": "11:30"})
    assert r.get("ok", True) is not False, r
    return agenda


def test_the_hour_he_asked_for_is_in_the_block_with_the_card_closed(_isolated_agenda):
    block = widget_read.read("agenda")
    assert "11:30" in block and "Tributaria" in block
    assert len(block) <= widget_read._MAX_BLOCK_CHARS


def test_a_widget_that_publishes_nothing_reads_as_empty_not_invented(monkeypatch):
    from widgets import refs
    monkeypatch.setattr(refs, "prompt_digest", lambda wid: "")
    monkeypatch.setattr(refs, "items_line", lambda wid: "")
    import importlib
    monkeypatch.setattr(importlib, "import_module", lambda name: (_ for _ in ()).throw(ImportError(name)))
    assert widget_read.read("clock") == ""
    assert widget_read.read("") == ""


# ── the second pass: the block is the ONLY source, an absence is stated ───────────────────────────────────
def test_compose_system_makes_the_block_the_only_source():
    sysp = widget_read.compose_system("LOCK", "¿a qué hora tengo la cita con Hacienda?", "agenda",
                                      "hora cita Hacienda", "  · 2026-09-11 11:30 «Cita Agencia Tributaria»")
    assert sysp.startswith("LOCK")
    assert "11:30" in sysp and "Cita Agencia Tributaria" in sysp
    W = __import__("i18n.langs", fromlist=["x"]).words("widget_read")                 # the instructions are the voice pack's, in his language (V2-831 audit A14)
    assert W["task"].format(name=widget_read.title("agenda"), wid="agenda") in sysp
    assert f"{W['looked_up']}: hora cita Hacienda" in sysp
    assert f"{W['his_words']}: ¿a qué hora tengo la cita con Hacienda?" in sysp


def test_a_SUMMARY_may_not_be_read_as_a_denial():
    """V2-704. The block is one of two things and an absence in it means opposite things.

    `answered=False` is the always-on digest, which for anything large is a first page and withholds fields by
    design. Measured 2026-09-15: asked four times for a contact's Telegram, the model got that digest — 15 rows
    of 2 686, platforms without handles — and answered «there's no Telegram handle stored». The handle was
    stored. The block's own first line («lo que no esté aquí NO está guardado», written when the directory had
    a dozen rows) is what turned "I did not see it" into a denial, so the prompt now outranks it explicitly.
    """
    digest = widget_read.compose_system("LOCK", "¿tienes el Telegram de X?", "contactos", "Telegram de X",
                                        "Directorio COMPLETO: 2686 entradas… lo que no esté aquí NO está "
                                        "guardado.\n· X (canales: telegram (preferido))\n… y 2671 más.")
    W = __import__("i18n.langs", fromlist=["x"]).words("widget_read")
    assert W["summary"] in digest, "the denial has to be forbidden in so many words"

    record = widget_read.compose_system("LOCK", "¿tienes el Telegram de X?", "contactos", "Telegram de X",
                                        "· «X» · telegram @equis ← CANAL PREFERIDO", answered=True)
    assert W["record"] in record
    assert W["summary"] not in record, "a resolved lookup must not be hedged as if it were a first page"


def test_the_piece_is_named_in_the_OPERATORS_language():
    """Every manifest in this repo is written in Castilian, and this path read `name` straight from it — so an
    English session heard «Let me check Contactos…» out loud and the second pass was told it had read «el widget
    "Contactos"». The translated label has existed since V2-694; this is the call that was not asking for it."""
    assert widget_read.title("contactos") == "Contacts"
    assert widget_read.title("agenda") == "Calendar"
    # …and a widget the bundles have never heard of still has a name, rather than losing one.
    assert widget_read.title("no-such-widget-anywhere") == "no-such-widget-anywhere"


def test_an_empty_block_is_declared_empty_never_filled():
    sysp = widget_read.compose_system("LOCK", "¿qué tengo el jueves?", "agenda", "", "")
    assert __import__("i18n.langs", fromlist=["x"]).words("widget_read")["empty"] in sysp


# ── both channels are wired (V2-252: parallel implementations drift unless both are read) ────────────────
def _code(rel: str) -> str:
    return re.sub(r"(?m)^\s*#.*$", "", _vts.read(rel))


# ── the OTHER light route the extraction moved: recall's voice pass had NO test at all (V2-668c) ──────────
# Found by a disarm that came back GREEN: deleting the voice channel's whole recall route broke nothing in the
# suite. It was untested before this batch too — moving it is the moment to cover it, because moving untested
# code is how a silent regression ships.
