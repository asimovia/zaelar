"""A task's exit door asks about a card act with the act's OWN question (`on_his_behalf.question`, V2-909).

A send task whose recipient the worker picked (`recipient: agent`) is asked before it leaves. The door used to ask
with the on-behalf line — «The background task wants to do «send_to» with «…» on your behalf…» — the act's raw id
and the word for our machinery read to him, where every other door asks the same act with its own sentence: who, by
which app, the draft. Now the door asks with `confirm_gate.own_question` (the sentence the turn's gate composes for
that act) and keeps the on-behalf line only for an act that declares none. The turn's gate is unchanged:
`_human_confirm_question` is `own_question`, else `_from_desc`, for every declared action.

Through the real door (`exit_gate.leave`), over an isolated directory, ES and EN.

Disarm (seen red, in memory): `own_question` answering '' → the door falls back to the on-behalf line, 2 reds.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from nucleo import on_his_behalf
from nucleo.workers import exit_gate
from voice.engine.llm.providers import confirm_gate
from widgets import runtime

SENDS = {
    "es": {"payload": {"contact": "Odile Varga", "text": "llego tarde", "platform": "whatsapp"},
           "heard": "manda un whatsapp diciendo que llego tarde", "other": "escríbele a Odile Varga que la llamo luego",
           "machinery": ("proceso", "en tu nombre")},
    "en": {"payload": {"contact": "Odile Varga", "text": "I am late", "platform": "whatsapp"},
           "heard": "send a whatsapp saying I am late", "other": "tell Odile Varga I'll call her later",
           "machinery": ("background task", "on your behalf")},
}
ACTS = sorted((m["id"], a) for m in runtime.catalog() for a, s in (m.get("actions") or {}).items()
              if isinstance(s, dict))


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
    cd.apply_action("add_contact", {"name": "Odile Varga", "phone": "611 204 377"})
    monkeypatch.setattr(playbook, "checkpoint_one", lambda rec: "")
    monkeypatch.setattr(contract, "would_refuse", lambda *a, **k: None)
    untrusted.reset()
    his_words.reset()

    def rec(tid, heard):
        return SimpleNamespace(task_id=tid, playbook_chosen="message", uid=tid, started=time.time(), depth=0,
                               trace_id="", surface="", sheet="", mandate={}, reading=None, heard=heard, own_words=True)
    yield SimpleNamespace(rec=rec, his_words=his_words)
    consent._reset_for_tests()
    untrusted.reset()
    his_words.reset()


def _ask_send(world, lang):
    v = SENDS[lang]
    world.his_words.note(v["other"], ts=time.time() - 60)     # she was named for ANOTHER order: the pick is the agent's
    ex = exit_gate.leave(world.rec(f"s-{lang}", [v["heard"]]), "widget_data",
                         {"widget_id": "mensajeria", "action": "send_to", "payload": dict(v["payload"])})
    assert ex.slots.get("recipient") == "agent" and ex.verdict == "ask", ex
    return ex.question, v


@pytest.mark.parametrize("lang", sorted(SENDS))
def test_a_send_whose_recipient_the_agent_picked_is_asked_with_the_send_sentence(world, monkeypatch, lang):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    q, v = _ask_send(world, lang)
    assert q == confirm_gate.own_question("mensajeria", "send_to", v["payload"]), q
    assert "Odile Varga" in q and v["payload"]["text"] in q and "WhatsApp" in q, q
    assert "send_to" not in q, q
    assert not any(m in q.lower() for m in v["machinery"]), q


@pytest.mark.parametrize("lang", sorted(SENDS))
def test_an_act_with_no_question_of_its_own_still_gets_the_on_behalf_line(monkeypatch, lang):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    from i18n import langs
    assert confirm_gate.own_question("mensajeria", "create_group", {}) == ""
    q = on_his_behalf.question("mensajeria", "create_group", {"name": "Cena"})
    who = on_his_behalf.shown_who("mensajeria", "create_group", {"name": "Cena"}) or "mensajeria"
    assert q == langs.current_language().worker_confirm_on_behalf.format(action="create_group", who=who), q


def test_an_unreadable_own_question_still_asks_with_the_on_behalf_line(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    from i18n import langs

    def boom(*a, **k):
        raise RuntimeError("unreadable")
    monkeypatch.setattr(confirm_gate, "own_question", boom)
    q = on_his_behalf.question("mensajeria", "send_to", {"contact": "Odile Varga", "text": "x"})
    assert q.startswith(langs.current_language().worker_confirm_on_behalf.split("«")[0]), q


@pytest.mark.parametrize("wid,action", ACTS, ids=[f"{w}:{a}" for w, a in ACTS])
def test_the_turns_gate_is_the_acts_own_question_else_its_description(wid, action):
    own = confirm_gate.own_question(wid, action, {})
    expected = own or confirm_gate._from_desc(wid, action, {})
    assert confirm_gate._human_confirm_question(wid, action, {}) == expected
    assert expected, f"{wid}:{action} has no question at all"


@pytest.mark.parametrize("wid,action,payload", [
    ("mensajeria", "reply", {"n": 1, "text": "ok"}),
    ("mensajeria", "send_to", {"contact": "Odile Varga", "text": "llego tarde", "platform": "whatsapp"}),
    ("mensajeria", "send_to", {"contact": "Odile Varga", "text": "llego tarde", "objective": "quedar el viernes"}),
    ("mensajeria", "forward", {"contact": "Odile Varga", "text": "mira esto"}),
    ("agenda", "clear_range", {}),
    ("agenda", "clear_all", {}),
])
def test_the_acts_that_compose_their_own_sentence_have_one(world, monkeypatch, wid, action, payload):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")
    q = confirm_gate.own_question(wid, action, payload)
    assert q and q == confirm_gate._human_confirm_question(wid, action, payload), q


def test_an_unknown_act_has_no_own_question_and_the_gate_asks_the_generic_line(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    assert confirm_gate.own_question("nowhere", "frobnicate", {}) == ""
    assert confirm_gate._human_confirm_question("nowhere", "frobnicate", {}) == confirm_gate._from_desc(
        "nowhere", "frobnicate", {}) != ""


@pytest.mark.parametrize("lang", sorted(SENDS))
def test_disarmed_a_door_without_the_acts_own_question_reads_the_on_behalf_line(world, monkeypatch, lang):
    """Disarm: `own_question` answers '' — the door asks with the on-behalf line and the send assertions go red."""
    monkeypatch.setattr(confirm_gate, "own_question", lambda *a, **k: "")
    with pytest.raises(AssertionError):
        test_a_send_whose_recipient_the_agent_picked_is_asked_with_the_send_sentence(world, monkeypatch, lang)
