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
from nucleo import wording
from nucleo.events import vocabulary as voc
from nucleo.request import send_errand, send_receipt
from nucleo.switchboard import act, board, route
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


# ── the router ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_new_request_is_nobodys_whatever_number_the_judge_gave(monkeypatch):
    """02:04:39 — one question waited («shall I send her the message?»), he ordered a group, and the judge answered
    `to: 1` with the reason «new request»: his order went into the old question and no turn ran for it."""
    from nucleo.memory_agent.processor import llm
    waits = [{"key": "r1", "title": "Message to Odile", "state": board.WAITING, "ask_id": "a1",
              "question": "The message for Odile is ready — shall I send it?"}]
    monkeypatch.setattr(llm, "chat_sync", lambda *a, **k: '{"to": 1, "is": "new", "why": "new request, not an answer"}')
    n, why, kind = route.ask_the_model("create a WhatsApp group with Odile called Shopping list", waits)
    assert n == 0 and "new request" in why, "the judge's own word decides: a new request reaches Flash"
    monkeypatch.setattr(llm, "chat_sync", lambda *a, **k: '{"to": 1, "is": "yes", "why": "go ahead"}')
    assert route.ask_the_model("yes, send it", waits)[::2] == (1, "yes"), "an answer still reaches its question"
    assert '"new"' in route.SYSTEM or "new" in route.SYSTEM.split("Reply with JSON")[1]


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


# ── his go-ahead ────────────────────────────────────────────────────────────────────────────────────────────────
def test_what_he_answered_on_the_row_is_read_with_the_order_and_the_judge_knows_the_act(world, monkeypatch):
    """02:07:00 — «create the group, I confirmed it twice, go ahead» answered the worker's own question; 13 s later the
    door read only the order and asked again."""
    from nucleo.circuit import ask_trace
    seen = []
    monkeypatch.setattr(act, "_go_ahead_model", lambda words, what="": seen.append((words, what)) or '{"confirmed": false}')
    rec = world.rec("g-3", "a message? I asked you for a group")
    assert act.read_his_go_ahead(rec, voc.of("messaging.send_new").what) is False and len(seen) == 1
    assert act.read_his_go_ahead(rec, "x") is False and len(seen) == 1, "nothing new said: not read again"
    ask_trace.keep_answer({"uid": "g-3", "question": "Shall I create the group now?"}, "create it, I confirmed twice, go ahead")
    monkeypatch.setattr(act, "_go_ahead_model", lambda words, what="": seen.append((words, what)) or '{"confirmed": true}')
    assert act.read_his_go_ahead(rec, voc.of("messaging.send_new").what) is True, "his answer is new words: read again"
    words, what = seen[-1]
    assert "go ahead" in words and "Shall I create the group now?" in words and what == "a message is sent to someone"
    assert "{what}" in act.GO_AHEAD, "the judge is told what the act is, never «a message» for everything"


# ── the lines ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_group_is_never_told_as_a_message(world, monkeypatch):
    """02:05:43 «I'm preparing the message», 02:07:26 «the message goes out now», 02:07:34 «the message is sent» — for
    a group. Each line is the fact of what the act IS, with what he asked for beside it."""
    from i18n import langs
    lang = langs.current_language()
    assert exit_risk.family("mensajeria", "create_group", GROUP) == "act"
    assert exit_risk.family("mensajeria", "send_draft", {"contact": "Odile Varga"}) == "send"
    assert [wording.line("act", m) for m in ("preparing", "going", "no", "done", "failed", "late")] == \
        ["act_preparing", "act_going", "act_not_done", "act_done", "act_failed", "act_unconfirmed"]
    for key in wording.LINES["act"].values():
        assert key in wording.FACTS and "message" not in wording.FACTS[key].lower(), key
        assert str(getattr(lang, key, "")), f"the language has no last-resort line for {key}"
    assert wording.ready("act") is wording.READY_ACT and wording.ready("send") is wording.READY
    retained = {"action": "widget_data", "payload": CALL}
    assert send_receipt.family_of(retained) == "act" and act.line_key({"key": "g-4"}, act.YES) in ("answer_taken", "work_started")
    from nucleo.circuit import asker
    monkeypatch.setattr(asker, "artefact", lambda uid: {"retained": retained})
    assert act.line_key({"key": "g-4"}, act.YES) == "act_going" and act.line_key({"key": "g-4"}, act.NO) == "act_not_done"


def test_the_worker_is_told_the_acts_own_steps_and_fields(monkeypatch):
    """02:07:39 — a worker read the whole card (30 KB) and searched it to learn how a group is created. The brief of an
    act that is not a message carries that act's declaration; a message keeps its own steps."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    brief = send_errand.brief_block({"playbook": "message", "send": {"widget": "mensajeria", "action": "create_group",
                                                                    "payload": {}}})
    assert "mensajeria:create_group" in brief and "members" in brief and "platform" in brief
    assert "widget data mensajeria create_group" in brief and "draft" not in brief
    msg = send_errand.brief_block({"playbook": "message", "send": {"widget": "mensajeria", "action": "send_to", "payload": {}}})
    assert "draft" in msg and "create_group" not in msg


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


# ── his no takes back what the request wrote ────────────────────────────────────────────────────────────────────
def test_his_no_takes_back_the_draft_the_request_wrote(world, monkeypatch):
    """Live, 02:45 — «no, don't send it» ended the send and the refused text stayed written in her chat box: one tap
    from being sent, and a draft «he had already seen» for a later order. His no (and his stop) clears what THIS
    request wrote there, with the act the card declares for it (`taken_back_by`); a request that wrote nothing clears
    nothing. (Disarmed on the real card below: writing an empty text is refused and clears nothing.)"""
    from nucleo.circuit import ledger
    calls = []
    fake = SimpleNamespace(apply_action=lambda action, payload: calls.append((action, dict(payload))) or {"ok": True})
    import importlib
    real = importlib.import_module
    monkeypatch.setattr(importlib, "import_module", lambda name, *a: fake if name == "widgets.mensajeria.data" else real(name, *a))
    rec = world.rec("n-1", "tell Odile good night")
    draft = {"widget_id": "mensajeria", "action": "draft", "payload": {"contact": "Odile Varga", "text": "good night"}}
    act.wrote(rec, "widget_data", draft)
    act.wrote(rec, "widget_data", {"widget_id": "mensajeria", "action": "send_draft", "payload": {"contact": "Odile Varga"}})
    assert (ledger.store().artifact_get("n-1", act.WRITTEN) or {}).get("call", {}).get("action") == "draft"
    assert send_errand.withdraw("n-1") is True
    assert calls == [("discard_draft", {"contact": "Odile Varga"})], "the act the card DECLARES takes it back"
    assert send_errand.withdraw("n-1") is False and len(calls) == 1, "taken back once"
    assert send_errand.withdraw(world.rec("n-2", "nothing written").uid) is False


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
