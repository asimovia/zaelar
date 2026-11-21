"""The phrasebook: a greeting is answered from a table, in any language, and nothing else is (V2-674).

Measured in the operator's own English session (sid fdd096a3, 2026-09-11) before a line was written:
«Hello and good morning. How are you?» → 3 440 ms of model covered by «Let me explain…»; «You were saying?»
→ «One sec, checking…» and then an INVENTED WhatsApp errand; «Hey, mate. You there?» → «Let me check that
for you…». None of the three is a request.

The asymmetry this file exists to hold: answering «hola» with a model costs three seconds, and answering a
real request with «¡Hola! Dime.» is a broken product. So the permissive cases are checked with one test each
and the REFUSING cases with many — a false positive here is the expensive direction.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


from nucleo.self import presence
from voice.engine.core import langs

ENGINE = Path(__file__).resolve().parents[4]


@pytest.fixture()
def es():
    return langs.smalltalk_book("es")


@pytest.fixture()
def en():
    return langs.smalltalk_book("en")


def test_a_knock_with_an_address_in_the_middle_is_still_a_knock(en, monkeypatch, tmp_path):
    """«Hey, mate. You there?» — the word standing between this sentence and the presence lane was «mate»."""
    from memory import db as memdb
    from nucleo.actionmap import store
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    monkeypatch.setattr(store, "active_lang", lambda: "en")
    store.invalidate()
    voc = tuple(en.get("vocatives") or ())
    assert presence.is_presence_check("Hey, mate. You there?", "", voc)
    assert presence.is_presence_check("You there?", "", voc)
    # …and an address with a REQUEST after it is not a knock, whatever the address.
    assert not presence.is_presence_check("mate, open the agenda", "", voc)


def test_every_how_are_you_reply_hands_the_question_back():
    """The intent is declared `bounces`, and the next turn's «bien» is gated on that. A pool where some
    replies ask back and some do not makes the gate fire after a reply that asked nothing."""
    for code in ("es", "en"):
        book = langs.smalltalk_book(code)
        for reply in book["intents"]["how_are_you"]["replies"]:
            assert "?" in reply, f"{code}: {reply!r} does not hand the question back"


def test_a_generated_pack_is_the_book_of_its_language(monkeypatch):
    """A shipped language reads its genesis book; any other reads the one generated for it at onboarding."""
    from i18n import packs
    fake = {"vocatives": ["mec"], "joiners": ["et"],
            "intents": {"greeting": {"cues": ["salut"], "replies": ["Salut !"]}}}
    monkeypatch.setattr(packs, "generated", lambda name, code: fake if (name, code) == ("smalltalk", "fr") else {})
    book = langs.smalltalk_book("fr")
    assert book["intents"]["greeting"]["replies"] == ("Salut !",)
    assert langs.smalltalk_book("es")["intents"]["thanks"]["replies"], "a shipped book is never replaced"


def test_the_generated_pack_never_carries_the_behavioural_flags():
    """`bounces` / `after_bounce` are rules about the CONVERSATION, not facts about the language. A pack that
    could set them would let a translator quietly change how the lane behaves."""
    from i18n.init import smalltalk as gen
    parsed = gen._parse('{"intents": {"greeting": {"cues": ["x"], "replies": ["y"], "bounces": true},'
                        ' "how_are_you": {"cues": ["z"], "replies": ["w"]}}}')
    assert parsed["intents"]["greeting"].get("bounces") is None
    assert parsed["intents"]["how_are_you"]["bounces"] is True


def test_a_pack_missing_half_an_intent_is_dropped_whole():
    """A cue with no replies would MATCH an utterance and then answer nothing — worse than no pack."""
    from i18n.init import smalltalk as gen
    assert gen._parse('{"intents": {"greeting": {"cues": ["hola"]}}}') == {}
    assert gen._parse('{"intents": {"invented": {"cues": ["a"], "replies": ["b"]}}}') == {}


# ── wiring: both channels, and the gates ────────────────────────────────────────────────────────────────
def _code(path: Path) -> str:
    """Source with comments and docstrings stripped — a guard that reads PROSE goes red when somebody
    documents the rule it enforces (V2-615's trap)."""
    import io
    import tokenize
    out, prev_end, prev_type = [], (1, 0), None
    from tests import voice_turn_source     # V2-778 F1: the voice turn is read whole, moved blocks included
    fh = io.BytesIO(voice_turn_source.read(path).encode("utf-8"))
    for tok in tokenize.tokenize(fh.readline):
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING and prev_type in (None, tokenize.INDENT, tokenize.NEWLINE,
                                                         tokenize.NL):
            continue
        out.append(tok.string)
        prev_end, prev_type = tok.end, tok.type
    return " ".join(out)
