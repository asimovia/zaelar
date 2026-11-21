"""A note he SAYS for the support team is written on the timeline, never a turn (INI-042 #37, the spoken half).

Measured: «quiero dejar un mensaje para soporte… tú no hace falta que hagas nada» became a turn — the agent opened a
document and asked whether to draft the feedback. A spoken note has no prefix: the sentence naming support only
PROPOSES it (the `voice` pack's words), the turn brief's `support_note` verdict decides, before the model.
"""
from __future__ import annotations


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

