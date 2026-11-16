"""The two measured regressions of the set-aside group series stay closed after V2-919 (fences of M1–M3).

The series reverted in 60f6ac31e had, measured by two audits and live replays: (1) with a draft held, a question
about it SENT the draft while its row stayed waiting; (2) `compose` became a send without his confirmation (an
unreadable end state closed checkpoint 1 for it). V2-919 reads what lacks from the declaration and gives the group
order a receipt; these tests hold that neither door moved:

  · a held draft whose call names nobody still asks «to whom» on its row and sends nothing — `send_draft` declares
    its `contact` optional, and the person a leaving act reaches is required whatever the payload says (es, en);
  · `compose` keeps its `done_when_unreadable`, and a retained compose is refused at checkpoint 1: nothing reaches
    the widget's door, whatever his words, with or without `send: true`.

Disarmed (seen red): `send_task_fields.required` reading only the payload declaration → the draft runs; a `done_when`
given to `compose` → the compose reaches the widget's door.
"""
from __future__ import annotations

import asyncio

import pytest

from memory import db as memdb, embeddings as mememb, tasks_store as ts
from nucleo import his_words, untrusted
from nucleo.request import inline_ask, model, send_task, send_task_run

WORDS = {"es": {"draft": "¿le mando el borrador así como está?", "compose": "escribe a Quinn que llego tarde y mándalo"},
         "en": {"draft": "should I send the draft as it is?", "compose": "write to Quinn that I'm late and send it"}}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    from nucleo import consent
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    monkeypatch.setattr(consent, "_overrides_path", lambda: tmp_path / "consent.json")
    consent._reset_for_tests()
    untrusted.reset()
    his_words.reset()
    inline_ask._RECENT.clear()
    inline_ask._TAKEN.clear()
    inline_ask._RESUMING.clear()
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
    inline_ask._RESUMING.clear()
    inline_ask._TAKEN.clear()
    consent._reset_for_tests()
    untrusted.reset()
    his_words.reset()
    memdb.reset_db()
    mememb.reset()


def _say(text: str) -> None:
    model.begin(text, trace="t-1")
    his_words.note(text)


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_held_draft_that_names_nobody_asks_and_sends_nothing(world, lang, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    said = WORDS[lang]["draft"]
    _say(said)
    uid = send_task.commission("mensajeria", "send_draft", {"key": "draft-1"}, said)
    assert uid and world["reached"] == [], "a held draft never leaves on a row with nobody named"
    assert send_task.missing(send_task.artefact(uid))[0] == "recipient"
    row = ts.task_get(uid)
    assert (row["state"], row["waiting_for"]) == ("waiting", "user_answer")


@pytest.mark.parametrize("lang", ["es", "en"])
@pytest.mark.parametrize("send", [None, True])
def test_compose_never_leaves_without_his_confirmation(world, lang, send, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    from widgets import effects
    assert effects.unattestable("mensajeria", "compose"), "compose keeps its done_when_unreadable"
    said = WORDS[lang]["compose"]
    _say(said)
    payload = {"to": "Quinn", "text": "llego tarde" if lang == "es" else "I'm late", "channel": "email",
               **({"send": send} if send is not None else {})}
    uid = send_task.retain("mensajeria", "compose", payload, said)
    assert uid
    res = asyncio.run(send_task_run.run(uid))
    assert world["reached"] == [], "checkpoint 1 is not relaxed for an act with no readable end state"
    assert res.get("ok") is False and "checkpoint 1" in str(res.get("error"))


def test_an_unread_declaration_fails_toward_asking(monkeypatch):
    from nucleo.flash import payload_fill
    from nucleo.request import send_task_fields
    monkeypatch.setattr(payload_fill, "_payload_spec", lambda *a: (_ for _ in ()).throw(RuntimeError("unread")))
    art = {"widget": "mensajeria", "action": "create_group", "slots": {"text": {"key": "text", "rule": "composed"}}}
    assert send_task_fields.required(art, "text") is True


@pytest.mark.xfail(strict=True, reason="OPEN CLASS (V2-919 audit): `take_call` fills a waiting send row from the "
                   "answering turn's call whatever that turn IS — a question about a held draft that names its addressee "
                   "fills the person and the draft leaves. Unchanged from main; recorded, not fixed in this pass.")
@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_question_about_a_held_draft_answered_by_the_models_call_sends_nothing(world, lang, monkeypatch):
    """The answering turn's own call (`take_call`) on a QUESTION about the draft that names its addressee — the path
    T4's first test does not cover (code unchanged from main)."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    from nucleo.request import send_task_answer
    from widgets import contract
    monkeypatch.setattr(contract, "would_refuse", lambda *a, **k: None)   # the draft to Luis Gil IS held
    said = "manda el borrador" if lang == "es" else "send the draft"
    _say(said)
    uid = send_task.commission("mensajeria", "send_draft", {"key": "draft-1"}, said)
    q = "¿qué pone en el borrador para Luis Gil?" if lang == "es" else "what does the draft to Luis Gil say?"
    _say(q)
    send_task_answer.take_call("mensajeria", "send_draft", {"key": "draft-1", "contact": "Luis Gil"}, q)
    assert world["reached"] == [], "a question about the draft never sends it"
