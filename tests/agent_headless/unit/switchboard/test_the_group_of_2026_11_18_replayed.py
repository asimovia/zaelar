"""«Create a WhatsApp group with her called Shopping list», replayed on what his engine did on 2026-11-18 (V2-931).

What he lived, read from that session's timeline: a question about a message already sent was still open, and his
order for the group fell into it — the router's own reason said «new request» and its number said 1; the group's task
then crossed the message door, which asked every act that leaves the same way: three times «the message for her is
written — shall I send it?», for a group; his «consider it confirmed» given with the order was read as no go-ahead
«to send»; his «yes, create it, go ahead» to the worker's own question was not read at all at the door; and when the
group was finally created he heard «the message is sent».

Each station, through the real code:

  · the router: a chunk the judge calls NEW is nobody's, whatever number came with it;
  · the exit door: a group with people he named is declared harmless and runs on his order, unasked; born with a
    first message it is a send and asks ONCE — its OWN question, never the message's;
  · his go-ahead: what he ANSWERED on the row is read with the order, and the judge is told what the act is;
  · the lines: a group's start, go-ahead and receipt are told as what he asked for, never as «the message»;
  · a request whose act already landed never asks about it nor runs it again.

Invented names only. Disarmed where it says so.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo.events import vocabulary as voc
from nucleo.request import send_errand, send_receipt
from nucleo.workers import exit_gate, exit_risk

GROUP = {"platform": "whatsapp", "name": "Shopping list", "members": ["Odile Varga"]}
CALL = {"widget_id": "mensajeria", "action": "create_group", "payload": GROUP}


@pytest.fixture
def world(tmp_path, monkeypatch):
    from nucleo import consent, his_words, untrusted
    from nucleo.workers.prompts import playbook
    from widgets import contract, store
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    monkeypatch.setattr(consent, "_overrides_path", lambda: tmp_path / "consent.json")
    consent._reset_for_tests()
    monkeypatch.setattr(playbook, "checkpoint_one", lambda rec: "")
    monkeypatch.setattr(contract, "would_refuse", lambda *a, **k: None)
    untrusted.reset()
    his_words.reset()

    def rec(uid, goal):
        ts.task_put({"id": uid, "title": goal[:60], "goal": goal, "state": "running", "created_at": int(time.time())})
        ts.task_patch(uid, playbook="message")
        return SimpleNamespace(task_id=uid, playbook_chosen="message", uid=uid, started=time.time(), depth=0,
                               trace_id="", surface="", sheet="", mandate={}, reading=None, heard=[goal], own_words=True)
    yield SimpleNamespace(rec=rec)
    consent._reset_for_tests()
    memdb.reset_db()


# ── the exit door ───────────────────────────────────────────────────────────────────────────────────────────────
def test_a_group_with_people_he_named_runs_on_his_order_and_is_never_asked(world):
    """02:05:47, 02:07:13, 02:07:46 — three questions for one group. The type declares it harmless: his order is the
    yes, the door releases it and its event says why."""
    assert voc.of("messaging.create_group").level == "standard" and not voc.asks_by_itself("messaging.create_group")
    assert exit_gate.leaves("mensajeria", "create_group"), "it still leaves: it crosses the door and is followed"
    ex = exit_gate.leave(world.rec("g-1", "create a WhatsApp group with Odile called Shopping list"), "widget_data", CALL)
    assert ex.verdict == "released" and not ex.question and not ex.refused, ex
    assert ex.event == "messaging.create_group@whatsapp" and "harmless" in ex.why
    # disarmed: a type nobody declared harmless asks — the rule reads the declaration, never the act's name
    assert voc.asks_by_itself("messaging.send_new") and voc.asks_by_itself("nothing.declared")


def test_a_group_born_with_a_first_message_is_a_send_and_asks_its_own_question_once(world, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    with_text = {**CALL, "payload": {**GROUP, "text": "we are out of milk"}}
    ex = exit_gate.leave(world.rec("g-2", "create a group with Odile called Shopping list and tell them hi"),
                         "widget_data", with_text)
    assert ex.verdict == "ask" and ex.event == "messaging.send_new@whatsapp", ex
    assert "Shopping list" in ex.question and "Odile Varga" in ex.question and "we are out of milk" in ex.question
    assert ex.question != exit_gate.ready_question("mensajeria", "send_to", {"contact": "Odile Varga"}), \
        "never the message's sentence for a group"
    assert exit_risk.family("mensajeria", "create_group", with_text["payload"]) == "act", "and it is told as a group"


def test_the_worker_is_told_the_acts_own_steps_and_fields(monkeypatch):
    """02:07:39 — a worker read the whole card (30 KB) and searched it to learn how a group is created. The brief of an
    act that is not a message carries that act's declaration; a message never reaches a worker (V2-938)."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    brief = send_errand.brief_block({"playbook": "message", "send": {"widget": "mensajeria", "action": "create_group",
                                                                    "payload": {}}})
    assert "mensajeria:create_group" in brief and "members" in brief and "platform" in brief
    assert "widget data mensajeria create_group" in brief and "draft" not in brief
    msg = send_errand.brief_block({"playbook": "message", "send": {"widget": "mensajeria", "action": "send_to", "payload": {}}})
    assert "create_group" not in msg


# ── an act that landed is final ─────────────────────────────────────────────────────────────────────────────────
def test_a_request_whose_act_already_landed_never_asks_about_it_again(world):
    """01:23 → 02:04 — a message already sent kept «shall I send it?» open on its row, and his next order fell into
    it. Once the receipt of an act is in, the same act of the same request is refused at the door: no question, no
    second run."""
    send = {"widget_id": "mensajeria", "action": "send_to", "payload": {"contact": "Odile Varga", "text": "good night"}}
    rec = world.rec("z-1", "tell Odile good night")
    assert exit_gate.leave(rec, "widget_data", send).verdict == "ask"
    send_receipt._mark_landed("z-1", "mensajeria", "send_to", {**send["payload"], "playbook": "message"})
    again = exit_gate.leave(rec, "widget_data", send)
    assert again.verdict == "refused" and "ALREADY DONE" in again.refused and not again.question
    other = {**send, "payload": {"contact": "Odile Varga", "text": "see you tomorrow"}}
    assert exit_gate.leave(rec, "widget_data", other).verdict == "ask", "other words are another act"
    assert exit_gate.leave(world.rec("z-2", "tell Odile good night"), "widget_data", send).verdict == "ask", \
        "another request is asked: only the request that sent it is done with it"


def test_the_real_card_takes_its_draft_back(tmp_path, monkeypatch):
    from widgets import effects, store
    from widgets.contactos import data as cd
    from widgets.mensajeria import data as md
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    cd.apply_action("add_contact", {"name": "Odile Varga", "phone": "611 204 377"})
    assert md.apply_action("draft", {"contact": "Odile Varga", "text": "good night", "channel": "whatsapp"})["ok"]
    assert not md.apply_action("draft", {"contact": "Odile Varga", "text": "", "channel": "whatsapp"}).get("ok"), \
        "disarmed: an empty text is not how a draft is taken back"
    undo = effects._manifest("mensajeria")["actions"]["draft"]["taken_back_by"]
    assert md.apply_action(undo, {"contact": "Odile Varga"})["ok"] and not (md.load_db().get("drafts") or {})
