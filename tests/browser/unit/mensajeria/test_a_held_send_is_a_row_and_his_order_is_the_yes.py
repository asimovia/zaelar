"""V2-800 — a send held for his word is a ROW of the mail card, a send for later is a scheduled row, and his explicit
order over a draft he has SEEN is the confirmation — decided by the one consent rule, the same for every channel.

The class (live, 2026-10-26): he asked for an email with exact text, «show it to me and wait for my "send it"». It
was shown in a document; the mail card knew nothing about it. His «send it» resolved to `send_draft` over whatever
reply draft was newest (or none), was asked TWICE (chat and a card overlay), and his yes sent nothing. Generic by
construction: email and WhatsApp below, an address and a contact, Spanish and English text.
"""
from __future__ import annotations

import asyncio
import threading
import time

import pytest

from nucleo import consent
from nucleo.acts import message as held_send
from widgets import store as wstore
from widgets.mensajeria import data, held


def _brief(target: str, conf: float, kind: str = "order") -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": ["mensajeria"],
            "result": {"screen_action": {"choice": target, "confidence": conf},
                       "request_type": {"choice": kind, "confidence": 1.0}}}


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(wstore, "_last_hash", {})
    from widgets.contactos import data as cd
    cd.apply_action("add_contact", {"name": "Rowan Pike", "phone": "+34600111222"})
    cd.apply_action("set_channel", {"contactId": "c1", "platform": "whatsapp", "handle": "+34600111222"})
    monkeypatch.setattr(consent, "_overrides_path", lambda: tmp_path / "consent.json")
    consent._reset_for_tests()
    # His turns: one arrives AFTER the draft is written (he has seen it) unless a test says otherwise.
    from nucleo import his_words
    monkeypatch.setattr(his_words, "since", lambda ts: ["send it"] if ts < time.time() + 1 else [])
    yield
    consent._reset_for_tests()
    # Process state the gate tests leave behind (the disarm leaves a pending question ON PURPOSE): a later voice
    # turn in the same process answered it instead of closing its card.
    from nucleo import his_words as _hw, untrusted
    from widgets import confirm as wc
    wc.reset()
    untrusted.reset()
    _hw.reset()


def _held_email():
    return data.apply_action("draft", {"contact": "hospitality@example.com", "subject": "API access",
                                       "text": "Hola,\n\nQueremos integrarnos con vuestra API."})


# ── the held draft is a row; nothing leaves when it is written ───────────────────────────────────────────

def test_a_new_message_held_for_his_word_is_a_draft_row_and_nothing_leaves():
    out = _held_email()
    from widgets.mensajeria.words import say
    assert out["ok"] and out["held"] and out["message"] == say("draft_ready", ""), out   # «check it», in his language
    db = data.load_db()
    assert not db.get("pending_send"), "writing the draft must not send it"
    rows = held.held(db)
    assert rows[0]["to"] == "hospitality@example.com" and rows[0]["subject"] == "API access"
    assert "BORRADOR esperando su OK" in data.__dict__["_held"].prompt_lines(db)[0]


def test_a_draft_for_a_chat_opens_her_conversation_with_the_text_in_its_box(monkeypatch):
    """V2-931 — the draft is read where it will leave from: writing it for a person whose conversation exists opens
    that conversation (as a send does), so the box he looks at holds the text. A person with no conversation yet, and
    a mail draft (it has its own screen), open no chat. Nothing leaves."""
    chat = {"ok": True, "platform": "whatsapp", "chatId": "34600111222@c.us", "name": "Rowan Pike", "contactId": "c1"}
    monkeypatch.setattr(data._outbound, "resolve_target", lambda payload=None: dict(chat))
    out = data.apply_action("draft", {"contact": "Rowan Pike", "text": "Good night"})
    assert out["ok"] and out["held"], out
    db = data.load_db()
    assert db.get("active_chat") == {"platform": "whatsapp", "chatId": "34600111222@c.us"}, db.get("active_chat")
    assert db["draft"]["text"] == "Good night" and not db.get("pending_send"), "written, never sent"
    assert str(db["draft"]["target"].get("chatId")) == "34600111222@c.us", "the box that holds it is that chat's"
    for none in ({**chat, "chatId": ""}, {**chat, "platform": "email", "chatId": "rowan@example.com"}):
        db = data.load_db()
        db["active_chat"] = None
        wstore.save(data.WIDGET_ID, db)
        monkeypatch.setattr(data._outbound, "resolve_target", lambda payload=None, t=none: dict(t))
        assert data.apply_action("draft", {"contact": "Rowan Pike", "text": "Good night"})["ok"]
        assert not data.load_db().get("active_chat"), none


def test_send_draft_named_by_its_recipient_sends_that_draft_with_its_subject():
    _held_email()
    data.apply_action("draft", {"contact": "Rowan Pike", "text": "See you at 4"})   # a second held draft, newer
    out = data.apply_action("send_draft", {"contact": "hospitality@example.com"})
    assert out["ok"], out
    q = data.load_db()["pending_send"]
    assert [(o["to"], o.get("subject")) for o in q] == [("hospitality@example.com", "API access")]
    assert [d["to"] for d in held.held(data.load_db())] == ["Rowan Pike"], "only the sent draft is gone"


# ── a send for later is a scheduled row: held until its time, visible, cancellable ─────────────────────

def test_a_send_for_later_waits_is_visible_and_is_cancelled():
    from connectors.messaging import store as msgstore
    _held_email()
    out = data.apply_action("send_draft", {"contact": "hospitality", "in_minutes": 600})
    assert out["ok"] and out["scheduled_for"] > time.time() + 590 * 60
    assert msgstore.take_pending_send() == [], "a scheduled send must not leave before its time"
    sent = data.view_data()["sent"]
    assert any(r.get("scheduled_for") for r in sent)
    assert any("PROGRAMADO" in l for l in held.prompt_lines(data.load_db()))
    assert data.apply_action("cancel_send", {})["ok"]
    assert not held.scheduled(data.load_db())


def test_an_unreadable_time_is_refused_not_sent_now():
    _held_email()
    out = data.apply_action("send_draft", {"contact": "hospitality", "at": "tonight-ish"})
    assert not out["ok"] and out["error"] == "bad_time"
    assert not data.load_db().get("pending_send")


# ── his order over a SEEN draft is the yes — one rule, every channel ───────────────────────────────────

def test_his_yes_clears_the_class_rail_and_never_his_own_ask_rule():
    lvl = {"level": "sensitive", "policy_key": "messaging.reply"}
    import rules
    rules.add(rules.GLOBAL, "gate", "ask_at", "sensitive")          # his global «ask before sensitive acts»
    assert consent.asks(consent.decide(**lvl))
    assert not consent.asks(consent.decide(**lvl, his_yes=True))
    consent.set_class("messaging.reply", "ask")
    assert consent.asks(consent.decide(**lvl, his_yes=True))


def test_the_same_inputs_give_every_channel_the_same_decision():
    for chan in ("email", "whatsapp", "telegram"):
        v = consent.decide(level="sensitive", policy_key=f"messaging.send_new@{chan}")
        assert v["verdict"] == consent.RUN, chan
        consent.set_class(f"messaging.send_new@{chan}", "ask")
        assert consent.asks(consent.decide(level="sensitive", policy_key=f"messaging.send_new@{chan}", his_yes=True))


def _worker_door(monkeypatch):
    """The REAL door a send crosses since V2-852 M2 — the turn routes it as a task and the worker's act goes through
    `worker_api.worker_act` → `exit_gate.gate` → the one asker; only the transport to the card is the real card's
    own `apply_action`, so what «left» is the card's outbox."""
    from types import SimpleNamespace

    from nucleo.cli import worker_api, worker_api_answer
    from widgets import server_api
    sent = []

    async def _brain_action(wid, act, payload):
        sent.append((wid, act, dict(payload)))
        return data.apply_action(act, dict(payload))
    monkeypatch.setattr(server_api, "brain_action", _brain_action)
    monkeypatch.setattr(worker_api, "_piggyback", lambda *_a: [])
    rec = SimpleNamespace(task_id="held", playbook_chosen="errand", uid="", started=time.time(), depth=0, trace_id="",
                          surface="", sheet="", native_sid="", waiting_on="", ask="", ask_corr="", parked=False,
                          mandate={})
    monkeypatch.setattr(worker_api, "_verify", lambda *_a: rec)
    monkeypatch.setattr(worker_api_answer, "_record_for", lambda _e: rec)
    from nucleo.pulse import notices
    from nucleo.send import owner

    async def _intake(said, hint=None, **kw):          # V2-938: what the door would ask is the message owner's
        return "?"

    async def _notify(*a, **kw):
        return {}
    monkeypatch.setattr(owner, "intake", _intake)
    monkeypatch.setattr(notices, "notify", _notify)

    def act(payload):
        import json
        out = asyncio.run(worker_api.worker_act(task_id="held", token="t", action="widget_data", payload={
            "widget_id": "mensajeria", "action": "send_draft", "payload": dict(payload)}))
        return json.loads(out.body)

    return SimpleNamespace(api=worker_api, act=act, sent=sent, rec=rec)


_QUINN = {"contact": "quinn@example.com"}


def _quinn_draft(text="Hi Quinn, Thursday at ten works for us."):
    data.apply_action("draft", {"contact": "quinn@example.com", "subject": "Thursday", "text": text})


def _asked(out: dict) -> bool:
    """He is asked: by the worker's row, or — a message, since V2-938 — by the message owner it was handed to."""
    return out.get("status") == "pending" or bool((out.get("result") or {}).get("handed"))


def _left():
    return [(o["to"], o.get("subject")) for o in (data.load_db().get("pending_send") or [])]


def test_a_pending_confirmation_has_one_surface_the_conversation():
    """«La confirmación se pide UNA vez, en UN sitio»: the chat thread holds the Yes/No (answerable there or by
    voice — both resolve the same pending row); the card overlay that repeated it is gone.

    Kept as a SOURCE check on purpose: which surface paints the question is `sse.js` routing, which cannot be
    driven from Python (the module pulls the store and the UI in at import). Its behaviour half — one row, one
    question emitted, either channel resolves it — is the test above."""
    import pathlib
    sse = (pathlib.Path(__file__).resolve().parents[4] / "frontend/app/services/sse.js").read_text(encoding="utf-8")
    block = sse[sse.index('else if (d.label === "confirm" && d.id) {'):][:900]
    assert "store.setWidgetConfirm(" in block
    assert "desktop.showConfirm(" not in block


def test_a_new_message_is_keyed_by_who_it_goes_to_never_by_an_empty_chat():
    """Two NEW messages to two people with no conversation yet must be two drafts — keyed by recipient."""
    _held_email()
    data.apply_action("draft", {"contact": "Rowan Pike", "text": "See you at 4"})
    keys = sorted(data.load_db()["drafts"])
    assert keys == ["to:email:hospitality@example.com", "to:whatsapp:+34600111222"], keys
