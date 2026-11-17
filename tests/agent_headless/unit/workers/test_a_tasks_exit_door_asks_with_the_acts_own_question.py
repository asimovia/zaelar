"""A task's exit door asks about a card act in a sentence of its own, never with machinery (V2-909, V2-931).

A send task is asked ONCE before it leaves. The door used to ask with the on-behalf line — «The background task wants
to do «send_to» with «…» on your behalf…» — the act's raw id and the word for our machinery read to him. Now a send is
asked with the ready line (`exit_gate.ready_question`, i18n `send_ready_confirm`) naming his contact; the on-behalf
line stays only for an act that declares no question of its own. The turn's gate is unchanged:
`_human_confirm_question` is `own_question`, else `_from_desc`, for every declared action.

Through the real door (`exit_gate.leave`), over an isolated directory, ES and EN.
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
    assert ex.verdict == "ask", ex
    return ex.question, v


@pytest.mark.parametrize("lang", sorted(SENDS))
def test_a_send_is_asked_with_the_ready_sentence_naming_her(world, monkeypatch, lang):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    q, v = _ask_send(world, lang)
    assert q == exit_gate.ready_question("mensajeria", "send_to", v["payload"]), q
    assert "Odile" in q and "Varga" not in q, "one short sentence: her name as he says it aloud"
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
    monkeypatch.setattr(on_his_behalf, "ACT_QUESTION", boom)
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


def test_a_manifest_question_fills_its_placeholders_from_the_payload_and_a_hole_is_no_question():
    q = confirm_gate.own_question("agenda", "invite", {"who": "Odile Varga", "meeting": "Budget review"})
    assert "Odile Varga" in q and "Budget review" in q and "{" not in q, q
    assert confirm_gate.own_question("agenda", "invite", {"who": "Odile Varga"}) == ""
    assert "{" not in confirm_gate._human_confirm_question("agenda", "invite", {"who": "Odile Varga"})


def test_the_lower_layer_reads_the_question_through_the_seam_the_gate_registers():
    assert on_his_behalf.ACT_QUESTION is confirm_gate.own_question
    src = open(on_his_behalf.__file__, encoding="utf-8").read()
    assert "voice.engine" not in src, "the lower layer never reaches into the motor's internals"
