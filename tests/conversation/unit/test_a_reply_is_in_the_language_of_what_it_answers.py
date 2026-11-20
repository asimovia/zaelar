"""A reply is in the language of what it answers, and he is never called by the assistant's name (node 13.98, V2-941,
v3.1 B7j — the corpus's R15).

The English corpus answered in Spanish 72 times (R15 3 → 36), most with no read at all, and called him «Johnny» — the
assistant's own name. The STATE the manager gave the model was the OLD turn's composed block: Spanish headings, Spanish
instructions to the model, a copy of the conversation in Spanish, and «Te llamas Johnny.» under «who is in front of
you». Now:
  · STATE is what the memory knows that is not the conversation, as FACTS with plain labels — the old composer is never
    read: no heading, no instruction, no copy of the conversation; the widgets by id; the tasks as facts;
  · the host's fixed lines are said in the language of the words they answer (the engine's own es/en reading of his
    batch), else the operator's, then English.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from conversation.ports import Done, Failed
from tests.conversation.unit.convkit import Harness


@pytest.fixture
def memory_facts(monkeypatch):
    from memory import api as memory
    monkeypatch.setattr(memory, "state", lambda: {"treatment": "w_tu", "location": "w_city", "operator_name": "Quinn"})
    monkeypatch.setattr(memory, "critical_facts", lambda limit=8: ["w_allergy"])
    monkeypatch.setattr(memory, "salient_long", lambda limit=8, max_chars=800: [
        {"text": "le gusta el café solo", "kind": "fact"}, {"text": "w_errand", "kind": "request"}])

    def never(*a, **k):
        raise AssertionError("the old turn's composed block is read")
    monkeypatch.setattr(memory, "compose_state", never)


def test_state_is_facts_with_plain_labels_never_the_old_prompt(memory_facts):
    from nucleo.conversation_host import memory_read
    text = memory_read._state()
    assert text.splitlines() == ["treatment: w_tu", "location: w_city", "critical: w_allergy",
                                 "known: le gusta el café solo", "he asked: w_errand"]


def test_widgets_and_tasks_are_facts_by_id(monkeypatch):
    from nucleo import dispatch
    from nucleo.circuit import ledger
    from nucleo.conversation_host import memory_read
    from nucleo.turn.prompt import live_state
    monkeypatch.setattr(live_state, "_open_widget_ids", lambda: ["agenda"])
    monkeypatch.setattr(live_state, "_recent_widget_ids", lambda: ["agenda", "weather"])
    from nucleo.flash import show_target
    from widgets import runtime
    monkeypatch.setattr(runtime, "catalog", lambda: [{"id": "agenda", "whenToUse": "w_days"}, {"id": "weather"}])
    monkeypatch.setattr(show_target, "at_full_screen", lambda: "agenda")
    assert memory_read._widgets() == ("agenda — w_days\nweather\non screen: agenda\nat full screen: agenda\n"
                                      "used lately: weather")
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [{"name": "w_job", "phase": "w_step", "done": 2,
                                                                 "total": 5, "pct": 40}])
    store = SimpleNamespace(tasks_where=lambda **kw: [{"id": "t1", "title": "w_goal", "waiting_for": ledger.USER_ANSWER,
                                                       "ask": "w_ask"}])
    monkeypatch.setattr(ledger, "store", lambda: store)
    assert memory_read._tasks().splitlines() == ["running: w_job · w_step · step 2/5 · 40%",
                                                 "waiting for his answer: [t1] w_goal — asked: w_ask"]


def test_a_fixed_line_is_in_the_language_of_his_words(monkeypatch):
    from i18n import langs
    from nucleo.conversation_host.words import PackWords
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec("es"))      # the operator's: Spanish
    en, es = langs.spec("en").unverified_fact, langs.spec("es").unverified_fact
    assert en != es
    assert PackWords().line("unverified_fact", near="what is the weather in the city today") == en
    assert PackWords().line("unverified_fact", near="qué tiempo hace hoy en la ciudad") == es
    assert PackWords().line("unverified_fact") == es                              # nothing to read: the operator's


def test_the_manager_hands_his_words_to_the_fixed_line(store):
    seen = []

    class _Words:
        def line(self, key, near=""):
            seen.append((key, near))
            return "w_lost"
    h = Harness(store, grace=False)
    h.conv.words = _Words()
    h.model.default = lambda ids: [Failed("w_boom", "provider")]
    h.typed("w1 w2", 10)
    h.settle(2000)
    assert ("mute_lines", "w1 w2") in seen
