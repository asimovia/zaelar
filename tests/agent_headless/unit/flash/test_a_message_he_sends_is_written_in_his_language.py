"""A message written FOR someone else goes in the session's language too (demo pass 105, 2026-10-04).

C5 «send rowan a telegram with the new time» in an English session: the model wrote «Oye Rowan, al final lo
movemos media hora más tarde…». The language lock spoke of the REPLY only; every tool description it reads is
Spanish, and the text it puts in a payload copied that. The lock now names those texts.
"""
from __future__ import annotations


def _lock(monkeypatch, code):
    from voice.engine.core import langs
    from nucleo.turn.prompt import builder as prompt
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec(code))
    return prompt._lang_lock()


def test_the_english_lock_covers_what_he_sends(monkeypatch):
    lock = _lock(monkeypatch, "en")
    assert "mensajes" in lock and "English" in lock.split("mensajes", 1)[1][:200], lock


def test_the_spanish_lock_says_it_too(monkeypatch):
    assert "mensajes" in _lock(monkeypatch, "es")


def test_his_dictated_words_are_not_the_locks_to_translate(monkeypatch):
    """V2-903 P1-1: the lock names the session language for what the model COMPOSES; what he dictates for someone
    else stays his words — the lock used to tell the model to translate «ya estamos…» in an English session."""
    for code in ("en", "es"):
        lock = _lock(monkeypatch, code)
        assert "DICTA" in lock and "tal cual" in lock.split("DICTA", 1)[1][:120], lock
