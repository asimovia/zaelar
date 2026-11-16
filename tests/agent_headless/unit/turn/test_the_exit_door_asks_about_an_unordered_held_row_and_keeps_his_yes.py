"""The exit door asks about a held row nobody surely ordered to deliver, and remembers his yes (node 2.1787).

Two halves of one class, found by the V2-919 audit on code that was already on main:

  · a declared `held` slot (a draft he saw) whose delivery no turn surely ordered read `agent` at the exit door, which
    asks nothing when the person is his — so the answering turn's own call on a QUESTION about the draft sent it. It
    now reads `unknown`: the door asks the act's own question. The commissioning turn's order covers the row as HE
    completed it; a value a later turn's call put on the row voids that order for the door (`order_void`).
  · his yes to the door's question was not remembered on the send-task path: the act crossed the door again, the same
    slot read the same, and the same question came back for ever. His yes is kept on the row with what it was said
    about (`send_task_run.consented`), so the question he answered is not asked again — and a payload that changed
    since is asked.

Disarmed (seen red): `_held` reading `agent` again → the draft is sent on the question turn; `consented` not written →
the second crossing asks again and nothing runs; the stamp ignored → a changed payload runs on the old yes.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from memory import db as memdb, embeddings as mememb
from nucleo import his_words, untrusted
from nucleo.request import inline_ask, model, send_task, send_task_answer, send_task_run

YES = {"es": "sí", "en": "yes"}
ORDER = {"es": "manda el borrador", "en": "send the draft"}
ASK = {"es": "¿qué pone en el borrador para Luis Gil?", "en": "what does the draft to Luis Gil say?"}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    from nucleo import consent
    from widgets import contract, store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    monkeypatch.setattr(consent, "_overrides_path", lambda: tmp_path / "consent.json")
    consent._reset_for_tests()
    untrusted.reset()
    his_words.reset()
    for bag in (inline_ask._RECENT, inline_ask._TAKEN, inline_ask._RESUMING):
        bag.clear()
    monkeypatch.setattr(contract, "would_refuse", lambda *a, **k: None)     # the act itself would run
    reached = []

    async def _dispatch(wid, action, payload, *, row="", text="", **kw):
        reached.append((wid, action, dict(payload)))
        return {"ok": True}
    from nucleo.flash import data_ops
    monkeypatch.setattr(data_ops, "dispatch_and_report", _dispatch)
    monkeypatch.setattr(send_task, "_schedule", lambda uid: asyncio.run(send_task_run.run(uid)))
    from nucleo.acts import errand
    monkeypatch.setattr(errand, "escalate_to_slowbrain",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("a worker was started")))
    yield {"reached": reached}
    model._TURN.set(None)
    for bag in (inline_ask._RESUMING, inline_ask._TAKEN):
        bag.clear()
    consent._reset_for_tests()
    untrusted.reset()
    his_words.reset()
    memdb.reset_db()
    mememb.reset()


def _say(text: str) -> None:
    model.begin(text, trace="t-1")
    his_words.note(text)


def _open_question(uid: str) -> dict:
    from nucleo.circuit import asker
    return dict(asker.artefact(uid))


def _held_draft_waits_on_the_door(lang: str) -> str:
    """A held draft, the person filled by a later turn's call: the row waits on the door's consent question."""
    _say(ORDER[lang])
    uid = send_task.commission("mensajeria", "send_draft", {"key": "draft-1"}, ORDER[lang])
    _say(ASK[lang])
    send_task_answer.take_call("mensajeria", "send_draft", {"key": "draft-1", "contact": "Luis Gil"}, ASK[lang])
    return uid


@pytest.mark.parametrize("lang", ["es", "en"])
def test_his_yes_to_the_doors_question_runs_the_act_once_and_is_not_asked_again(world, lang, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    from nucleo import consent
    uid = _held_draft_waits_on_the_door(lang)
    q = _open_question(uid)
    assert world["reached"] == [] and q.get("consent") == consent.ASK_CONSENT
    got = send_task_answer.answered(uid, q, YES[lang])
    assert got.get("ok") is True
    assert [(w, a) for w, a, _p in world["reached"]] == [("mensajeria", "send_draft")], "his yes ran it, once"
    after = _open_question(uid)
    assert after.get("ask_id") == q.get("ask_id"), "no second question was opened after his yes"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_no_sends_nothing(world, lang, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    uid = _held_draft_waits_on_the_door(lang)
    send_task_answer.answered(uid, _open_question(uid), "no")
    assert world["reached"] == []


def test_a_yes_covers_only_the_payload_it_was_said_about(world, monkeypatch):
    """The yes is stamped with the payload; a payload changed afterwards crosses the door as a new act and is asked."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    uid = _held_draft_waits_on_the_door("en")
    send_task_run.consented(uid)
    art = send_task.artefact(uid)
    assert art["consented"] == send_task_run.stamp(art["payload"])
    art["payload"]["contact"] = "Quinn Xavier"            # somebody else, after the yes
    send_task._keep(uid, art)
    asyncio.run(send_task_run.run(uid))
    assert world["reached"] == [], "the old yes does not cover another person"


@pytest.mark.parametrize("void, want", [(False, "held"), (True, "unknown")])
def test_an_order_voided_by_a_later_call_is_not_read_at_the_door(monkeypatch, void, want):
    """His sure order releases the held row; the same order is not read once a later turn's call changed the row."""
    from nucleo.acts import message
    from nucleo.workers import exit_slots, taint
    monkeypatch.setattr(message, "confirmed", lambda *a, **k: True)
    monkeypatch.setattr(taint, "tainted", lambda rec: False)
    out = exit_slots.Reading({"key": "draft-1", "contact": "Luis Gil"})
    ctx = {"rec": SimpleNamespace(order_void=void), "wid": "mensajeria", "act": "send_draft", "said": "",
           "turn": object(), "emit": lambda *a, **k: None, "tainted": False, "row_call": False}
    exit_slots._held(ctx, out, "draft", "key")
    assert out.sources["draft"] == want and out.released is (not void)


def test_a_held_row_read_after_a_strangers_text_is_the_taints_question(monkeypatch):
    """Unordered and tainted: the slot stays `stranger` (the taint asks), never downgraded to a plain doubt."""
    from nucleo.acts import message
    from nucleo.workers import exit_slots
    monkeypatch.setattr(message, "confirmed", lambda *a, **k: False)
    out = exit_slots.Reading({"key": "draft-1"})
    ctx = {"rec": SimpleNamespace(), "wid": "mensajeria", "act": "send_draft", "said": "", "turn": None,
           "emit": lambda *a, **k: None, "tainted": True, "row_call": False}
    exit_slots._held(ctx, out, "draft", "key")
    assert out.sources["draft"] == "stranger"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_his_sure_order_covers_his_own_answer_but_not_a_later_calls_value(world, lang, monkeypatch):
    """He surely ordered the draft sent (the commissioning turn's order, here `confirmed`), and the row asked «to
    whom». HIS answer completes what he ordered: it leaves with no further question. The same person put on the row
    by a later turn's CALL was never part of his order: the door asks, nothing leaves."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    from nucleo import consent
    from nucleo.acts import message
    monkeypatch.setattr(message, "confirmed", lambda *a, **k: True)
    _say(ORDER[lang])
    uid = send_task.commission("mensajeria", "send_draft", {"key": "draft-1"}, ORDER[lang])
    got = send_task_answer.answered(uid, _open_question(uid), "Luis Gil")
    assert got.get("ok") is True and [(w, a) for w, a, _p in world["reached"]] == [("mensajeria", "send_draft")]
    world["reached"].clear()
    other = _held_draft_waits_on_the_door(lang)
    assert world["reached"] == [], "a value the later call added is not covered by his order"
    assert _open_question(other).get("consent") == consent.ASK_CONSENT
    assert send_task.artefact(other).get("order_void") is True
