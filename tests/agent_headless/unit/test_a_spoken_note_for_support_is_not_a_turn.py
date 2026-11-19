"""A note he SAYS for the support team is written on the timeline, never a turn (INI-042 #37, the spoken half).

Measured: «quiero dejar un mensaje para soporte… tú no hace falta que hagas nada» became a turn — the agent opened a
document and asked whether to draft the feedback. A spoken note has no prefix: the sentence naming support only
PROPOSES it (the `voice` pack's words), the turn brief's `support_note` verdict decides, before the model.
"""
from __future__ import annotations

import asyncio
import inspect
import re

import pytest

from nucleo.input import support_note

NOTE_ES = "quiero dejar un mensaje para soporte, la voz se corta al final; tú no hace falta que hagas nada"


@pytest.fixture
def spanish(monkeypatch):
    from i18n import langs
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec("es"))


def test_naming_support_proposes_a_note_in_his_language(spanish):
    assert support_note.proposes(NOTE_ES)
    assert support_note.proposes("Leave this for SUPPORT: the wall doubled")     # English rides under every language
    assert not support_note.proposes("pon una cita con el dentista el viernes")
    assert not support_note.proposes("es un soportal precioso")                  # a word, not a substring


def test_the_brief_asks_only_when_proposed(spanish):
    assert support_note.question({"operator_text": NOTE_ES})["criteria"].keys() == {"note", "turn"}
    assert support_note.question({"operator_text": "abre la agenda"}) is None
    from nucleo.turn import brief
    assert support_note.KEY in brief.asked_keys()


@pytest.mark.parametrize("verdict, info, is_note", [("note", {"used": True}, True),
                                                    ("turn", {"used": True}, False),
                                                    ("note", None, False)])          # late or unreadable = a turn
def test_the_verdict_decides_and_a_note_is_recorded_not_answered(spanish, monkeypatch, verdict, info, is_note):
    from nucleo.turn import brief
    events, said, asked = [], [], []

    async def _verdict(text, key, wait_s=2.0):
        asked.append(key)
        return verdict, info
    monkeypatch.setattr(brief, "verdict_before_the_turn", _verdict)
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: events.append((a, k)))

    assert asyncio.run(support_note.heard(NOTE_ES, said.append)) is is_note
    assert asked == [support_note.KEY]
    notes = [kw for a, kw in events if a[0] == "feedback" and kw["extra"].get("support_note")]
    assert len(notes) == (1 if is_note else 0)
    if is_note:
        assert notes[0]["text"] == NOTE_ES and notes[0]["role"] == "user"
        assert len(said) <= 1, "at most a minimal acknowledgement"


def test_a_sentence_that_names_no_support_pays_nothing(spanish, monkeypatch):
    from nucleo.turn import brief

    waited = []

    async def _never(*a, **k):
        waited.append(a)
        return "note", {"used": True}
    monkeypatch.setattr(brief, "verdict_before_the_turn", _never)
    assert asyncio.run(support_note.heard("abre la agenda del viernes")) is False
    assert waited == [], "a turn that names no support waits for no verdict"


def test_the_turn_gate_ends_the_turn_on_a_note_before_the_switchboard():
    from nucleo.turn import pipeline_gate
    src = inspect.getsource(pipeline_gate.open_the_turn)
    gate = re.search(r'if not first_turn and \(await __import__\("nucleo\.input\.support_note", fromlist=\["x"\]\)'
                     r'\.heard\(text, self\._out\)\s*\n\s*or await __import__\("nucleo\.switchboard\.route"[^\n]*\)\):'
                     r'\s*\n\s*return None', src)
    assert gate, "a note ends the turn at the gate, before the switchboard reads it"
    assert -1 < src.find("hold_a_fragment") < gate.start(), "the note is read on the WHOLE sentence"
