"""A group he ordered, with the members he named, leaves a task's exit door without a question (2.1761).

`mensajeria:create_group` declared no recipient slot and no question of its own, so every group a worker created was
asked at the exit door with the on-behalf line — the act's raw id and «you didn't ask me for that» — even when his
words for the errand named every member. The act now declares its slots (recipient ← `members` from his words,
channel ← `platform` from the reading, text composed) and its own sentence; a LIST recipient is his only when every
member is in his words (`exit_slots._his_words`), and a list placeholder of the sentence reads as the names joined
(`confirm_gate.own_question`).

Through the real door (`exit_gate.leave`), over an isolated directory, ES and EN:
  · every member named (full names, or first names the directory gives to one person each) → passes, no question;
  · the same after the session read a stranger's text, with the turn's reading naming the channel → passes;
  · one member he never named → asked with the act's own sentence (the group and its members), no act id and no
    on-behalf wording;
  · no group name in the payload → the sentence has a hole → the on-behalf line asks.

Disarm (seen red, in memory): a list recipient read as the agent's (the pre-list reading) → the named group is asked.
"""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from nucleo.workers import exit_gate, exit_slots, taint
from voice.engine.llm.providers import confirm_gate   # registers the act's own question on the lower layer

MEMBERS = ["Odile Varga", "Bruno Keller"]
STRANGER = "Mireia Sala"
WORDS = {
    "es": {"full": "crea un grupo de whatsapp que se llame Cena con Odile Varga y Bruno Keller",
           "first": "crea un grupo de whatsapp que se llame Cena con Odile y Bruno",
           "name": "Cena", "machinery": ("proceso", "en tu nombre")},
    "en": {"full": "create a whatsapp group called Dinner with Odile Varga and Bruno Keller",
           "first": "create a whatsapp group called Dinner with Odile and Bruno",
           "name": "Dinner", "machinery": ("background task", "on your behalf")},
}


@pytest.fixture
def world(tmp_path, monkeypatch):
    from nucleo import consent, his_words, untrusted
    from nucleo.workers.prompts import playbook
    from widgets import contract, store
    from widgets.contactos import data as cd
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    monkeypatch.setattr(consent, "_overrides_path", lambda: tmp_path / "consent.json")
    consent._reset_for_tests()
    for name, phone in (("Odile Varga", "611 204 377"), ("Bruno Keller", "622 315 488"), (STRANGER, "633 426 599")):
        cd.apply_action("add_contact", {"name": name, "phone": phone})
    monkeypatch.setattr(playbook, "checkpoint_one", lambda rec: "")
    monkeypatch.setattr(contract, "would_refuse", lambda *a, **k: None)
    untrusted.reset()
    his_words.reset()

    def rec(tid, heard, reading=None):
        return SimpleNamespace(task_id=tid, playbook_chosen="message", uid=tid, started=time.time(), depth=0,
                               trace_id="", surface="", sheet="", mandate={}, reading=reading, heard=[heard],
                               own_words=True)
    yield SimpleNamespace(rec=rec)
    consent._reset_for_tests()
    untrusted.reset()
    his_words.reset()


def _whatsapp_reading():
    from nucleo.turn import brief as tb
    ev = threading.Event()
    ev.set()
    return tb.carried({"event": ev, "turn_id": "t-1", "open_ids": [],
                       "result": {"message_channel": {"choice": "whatsapp", "confidence": 0.97}}})


def _group(world, tid, heard, members, *, name="", reading=None, tainted=False):
    r = world.rec(tid, heard, reading)
    if tainted:
        taint.mark(r, "recall:messages")
    p = {"platform": "whatsapp", "members": list(members), **({"name": name} if name else {})}
    return exit_gate.leave(r, "widget_data", {"widget_id": "mensajeria", "action": "create_group", "payload": p})


@pytest.mark.parametrize("lang", sorted(WORDS))
@pytest.mark.parametrize("said,members", [("full", MEMBERS), ("first", MEMBERS), ("first", ["Odile", "Bruno"])])
def test_a_group_whose_every_member_he_named_passes_unasked(world, monkeypatch, lang, said, members):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    w = WORDS[lang]
    ex = _group(world, f"a-{lang}-{said}", w[said], members, name=w["name"])
    assert ex.slots.get("recipient") == "his" and ex.verdict == "pass" and not ex.question, ex


@pytest.mark.parametrize("lang", sorted(WORDS))
def test_a_tainted_session_with_his_channel_read_still_passes_the_group_he_named(world, monkeypatch, lang):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    w = WORDS[lang]
    ex = _group(world, f"b-{lang}", w["full"], MEMBERS, name=w["name"], reading=_whatsapp_reading(), tainted=True)
    assert ex.slots.get("recipient") == "his" and ex.slots.get("channel") == "reading", ex
    assert ex.verdict == "pass" and not ex.question, ex


@pytest.mark.parametrize("lang", sorted(WORDS))
def test_a_member_he_never_named_is_asked_with_the_acts_own_sentence(world, monkeypatch, lang):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    w = WORDS[lang]
    ex = _group(world, f"c-{lang}", w["full"], MEMBERS + [STRANGER], name=w["name"])
    assert ex.slots.get("recipient") == "agent" and ex.verdict == "ask", ex
    q = ex.question
    assert q == confirm_gate.own_question("mensajeria", "create_group",
                                          {"platform": "whatsapp", "name": w["name"], "members": MEMBERS + [STRANGER]})
    assert w["name"] in q and all(m in q for m in MEMBERS + [STRANGER]), q
    assert "create_group" not in q and not any(m in q.lower() for m in w["machinery"]), q
    assert ("Shall I" in q) == (lang == "en"), f"the sentence is not in {lang}: {q}"


@pytest.mark.parametrize("lang", sorted(WORDS))
def test_a_group_with_no_name_has_no_sentence_and_the_on_behalf_line_asks(world, monkeypatch, lang):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    from i18n import langs
    w = WORDS[lang]
    ex = _group(world, f"d-{lang}", w["full"], MEMBERS + [STRANGER])
    assert ex.verdict == "ask", ex
    assert ex.question.startswith(langs.current_language().worker_confirm_on_behalf.split("«")[0]), ex.question


def _slot(value, said="text Odile Varga and Bruno Keller"):
    out = exit_slots.Reading({"members": value})
    exit_slots._his_words({"row_call": False, "said": said, "tainted": False}, out, "recipient", "members")
    return out.sources["recipient"]


def test_a_list_recipient_is_his_only_when_every_member_is(world):
    assert _slot(MEMBERS) == "his"
    assert _slot(MEMBERS + [STRANGER]) == "agent"
    assert _slot([]) == "none"
    assert _slot(["Odile Varga", "", None]) == "his", "empty items are no member"
    assert _slot(["Odile Varga", 7]) == "agent", "a member that is not a name is not his"


def test_a_list_placeholder_reads_as_the_names_joined(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    q = confirm_gate.own_question("mensajeria", "create_group", {"name": "Dinner", "members": MEMBERS})
    assert "Odile Varga, Bruno Keller" in q and "[" not in q and "{" not in q, q
    assert confirm_gate.own_question("mensajeria", "create_group", {"name": "Dinner", "members": []}) == ""


def test_the_group_declares_its_slots():
    assert exit_slots.declared("mensajeria", "create_group") == {
        "recipient": {"key": "members", "from": "his_words", "many": True},   # several people (2.1776)
        "channel": {"key": "platform", "from": "reading"}, "text": {"key": "text", "from": "composed"}}


@pytest.mark.parametrize("lang", sorted(WORDS))
def test_disarmed_a_list_read_as_the_agents_asks_the_group_he_named(world, monkeypatch, lang):
    """Disarm: a list recipient read as the agent's own (the reading before lists) → the named group is asked."""
    real = exit_slots._his_words

    def pre_list(ctx, out, slot, key):
        if isinstance(out.inner.get(key), (list, tuple)):
            out.sources[slot] = exit_slots._own(ctx, out.inner.get(key))
            return
        real(ctx, out, slot, key)
    monkeypatch.setitem(exit_slots.RULES, "his_words", pre_list)
    with pytest.raises(AssertionError):
        test_a_group_whose_every_member_he_named_passes_unasked(world, monkeypatch, lang, "full", MEMBERS)
