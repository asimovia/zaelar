"""The first-run presentation is owed once to the manager too (node 13.133, INI-078 F2 step 7c, row 10): while it was
never said on this install, his language is chosen and the introduction is not over, every run carries it as a block of
its state — the language pack's own words with the agent's current name, framed by a declared fact; the batch whose
reply NAMED the agent settles it for good (and the name-and-voice offer it carries), a reply that did not name it leaves
it owed; once said, no run carries it."""
from __future__ import annotations

import pytest

from nucleo.conversation_host import memory_read, record
from nucleo.self import presentation


@pytest.fixture
def install(monkeypatch):
    from i18n import langs
    from nucleo.self import snapshot
    store: dict = {"stt_language": "en"}
    monkeypatch.setattr("config.settings.get", lambda k, d=None: store.get(k, d))
    monkeypatch.setattr("config.settings.update", lambda patch: store.update(patch))
    monkeypatch.setattr(snapshot, "name", lambda: "W_Zed")
    monkeypatch.setattr(langs, "words", lambda key, *a, **k: "I'm {name}, what is your name?"
                        if key == "introduction.presentation" else "")
    monkeypatch.setattr(record, "_ingest", lambda said, channel: None)
    monkeypatch.setattr("memory.api.write", lambda *a, **k: None)
    return store


def _carried() -> str:
    return " ".join(b.text for b in memory_read._blocks(4000) if b.title == "PRESENT")


def test_every_run_carries_it_until_a_reply_names_the_agent(install):
    assert "«I'm W_Zed, what is your name?»" in _carried()
    record.MemoryRecord().pair("acct", "w_hello", "Hi, nice to meet you.", ref="r1")
    assert memory_read._present() and not install.get(presentation.FLAG)       # did not name it: still owed
    record.MemoryRecord().pair("acct", "w_hello", "I'm W_Zed. What is your name?", ref="r2")
    assert install[presentation.FLAG] is True and install[presentation.OFFER_FLAG] is True
    assert _carried() == ""


def test_nothing_is_owed_before_his_language_or_after_the_introduction(install):
    install.pop("stt_language")
    assert memory_read._present() == ""
    install.update(stt_language="en", intro_done=True)
    assert memory_read._present() == ""
