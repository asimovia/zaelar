"""A send reaches the person he named, or asks ONE «which?» — never a guess (V2-847, multi-turn bench 2026-11-12).

Two Raquels on WhatsApp, both talked to this week, and one mail from Ana López in the inbox:

  · «escríbele a Raquel…» → the model wrote «Raquel Salvador Esteban»: his «Raquel» reaches two people alike, so the
    recipient is the agent's pick. The send's row asks «which Raquel?» with both as candidates, nothing is sent, and his
    answer «Raquel Jofre» fills that slot on the SAME row, which runs (`send_task_who.which`);
  · «send Raquel a WhatsApp…» → the model called `reply {n: 1}`, which answers whoever wrote row 1 — Ana López, whom he
    never named. The act becomes the card's act that writes to a person, with HIS person and the same words; the next
    turn's «Raquel Jofre» with `n: 1` again goes to Raquel Jofre (`send_task_who.readdressed`);
  · a reply to the person he named («contéstale a Ana») stays a reply; one Raquel he talks to (CRIT-M12's margin) is
    his and asks nothing.

Disarm: `which` → None (the guess runs); `readdressed` returns the call as it came (the reply goes to Ana) → red.
"""
from __future__ import annotations

import time

import pytest

from memory import db as memdb, embeddings as mememb, tasks_store as ts
from nucleo import his_words, untrusted
from nucleo.circuit import asker
from nucleo.request import inline_ask, model, send_task, send_task_answer, send_task_who

WID = "mensajeria"
WORDS = {"es": ("Mándale un whatsapp a Raquel diciéndole que llego tarde", "llego tarde", "A Raquel Jofre",
                "Contéstale a Ana que me parece bien el presupuesto", "me parece bien el presupuesto"),
         "en": ("Send Raquel a WhatsApp saying I'm running late", "I'm running late", "Raquel Jofre",
                "Reply to Ana that the budget looks fine", "the budget looks fine")}
INBOX = {"platforms": {"whatsapp": {"status": "connected"}, "email": {"status": "connected"}},
         "items": [{"platform": "email", "messageId": "m-1", "chatId": "ana.lopez@example.org",
                    "senderId": "ana.lopez@example.org", "from": "Ana López", "isGroup": False,
                    "subject": "Presupuesto", "body": "4.200 €", "ts": time.time() - 3600}]}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    from nucleo import consent
    from widgets import contract, directory, store
    from widgets.contactos import data as cd
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    monkeypatch.setattr(consent, "_overrides_path", lambda: tmp_path / "consent.json")
    consent._reset_for_tests()
    for name, phone in (("Raquel Salvador", "600 111 222"), ("Raquel Jofre", "680 762 886")):
        cd.apply_action("add_contact", {"name": name, "phone": phone})
        jid = "34" + phone.replace(" ", "") + "@s.whatsapp.net"
        assert directory.note_inbound("whatsapp", {"chatId": jid, "senderId": jid, "from": name})
    store.save(WID, dict(INBOX))
    monkeypatch.setattr(contract, "would_refuse", lambda *a, **k: None)
    untrusted.reset()
    his_words.reset()
    for d in (inline_ask._RECENT, inline_ask._TAKEN, inline_ask._RESUMING):
        d.clear()
    sent, events = [], []

    async def _dispatch(wid, action, payload, *, row="", text="", **kw):
        sent.append({"widget": wid, "action": action, "payload": dict(payload), "row": row})
        return {"ok": True}
    from nucleo.flash import data_ops
    monkeypatch.setattr(data_ops, "dispatch_and_report", _dispatch)
    import voice.observer as _obs
    real = _obs.emit
    monkeypatch.setattr(_obs, "emit", lambda kind, label, text="", role="", extra=None, **kw:
                        events.append({"kind": kind, "label": label, "text": text, **(extra or {})})
                        or real(kind, label, text=text, role=role, extra=extra))
    yield {"sent": sent, "events": events}
    model._TURN.set(None)
    for d in (inline_ask._RESUMING, inline_ask._TAKEN):
        d.clear()
    consent._reset_for_tests()
    untrusted.reset()
    his_words.reset()
    memdb.reset_db()
    mememb.reset()


def _say(text: str) -> None:
    model.begin(text, trace="t-1")
    his_words.note(text)


def _asks(world):
    return [e for e in world["events"] if e["kind"] == "ask"]


def _rows():
    return ts.tasks_where(states=("waiting", "running", "done", "failed", "cancelled"), visible_only=False)


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_name_that_reaches_two_people_alike_is_one_which_question_on_the_row(world, lang, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    said, text, answer, *_ = WORDS[lang]
    _say(said)
    uid = send_task.commission(WID, "send_to", {"contact": "Raquel Salvador", "text": text, "channel": "whatsapp"}, said)
    assert uid and world["sent"] == [], "the agent's pick between two Raquels was sent"
    asks = _asks(world)
    assert len(asks) == 1 and asks[0]["task_id"] == uid
    entry = asker.artefact(uid)
    assert sorted(entry["candidates"]) == ["Raquel Jofre", "Raquel Salvador"] and entry["consent"] == "ask_which"
    assert "Raquel Jofre" in asks[0]["text"] and "Raquel Salvador" in asks[0]["text"]
    _say(answer)
    got = send_task_answer.answered(uid, entry, answer, choice=entry["candidates"].index("Raquel Jofre"))
    assert got["ok"] and len(world["sent"]) == 1 and world["sent"][0]["row"] == uid
    assert world["sent"][0]["payload"]["contact"] == "Raquel Jofre"
    assert len(_rows()) == 1, "the same row, no second task"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_his_own_word_that_reaches_two_people_alike_is_asked_on_the_row_too(world, lang, monkeypatch):
    """The card's usage asks the model to pass the name AS HE SAID IT («Raquel»): the row asks before it runs, and the
    answering turn's own call fills it — one row, one send, to the one he chose."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    said, text, answer, *_ = WORDS[lang]
    _say(said)
    uid = send_task.commission(WID, "send_to", {"contact": "Raquel", "text": text, "channel": "whatsapp"}, said)
    assert world["sent"] == [] and len(_asks(world)) == 1
    _say(answer)
    assert send_task_answer.take_call(WID, "send_to", {"name": "Raquel Jofre", "text": text}, answer) == uid
    assert [s["payload"]["contact"] for s in world["sent"]] == ["Raquel Jofre"] and len(_rows()) == 1


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_reply_to_someone_he_did_not_name_is_a_message_to_the_one_he_named(world, lang, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    said, text, answer, *_ = WORDS[lang]
    wid, act, payload = send_task_who.readdressed(WID, "reply", {"n": 1, "text": text}, said)
    assert act == "send_to", "a reply to Ana López for a message he asked to send to Raquel"
    assert payload["text"] == text and "ana" not in str(payload).lower()
    assert payload["contact"].lower() == "raquel"            # his word: the card or the row asks which Raquel
    _wid, act2, payload2 = send_task_who.readdressed(WID, "reply", {"n": 1, "text": text}, answer)
    assert (act2, payload2.get("contact")) == ("send_to", "Raquel Jofre")


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_reply_to_the_person_he_named_stays_a_reply(world, lang, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    *_, said, text = WORDS[lang]
    assert send_task_who.readdressed(WID, "reply", {"n": 1, "text": text}, said) == (WID, "reply",
                                                                                    {"n": 1, "text": text})


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_raquel_he_talks_to_is_his_and_nothing_is_asked(world, lang, monkeypatch):
    """CRIT-M12: one Raquel leads by a recent conversation (the other was never talked to) — his «Raquel» is her."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    from widgets.contactos import data as cd
    db = cd.load_db()
    for c in db["contacts"]:
        if c.get("name") == "Raquel Jofre":
            for ch in c.get("channels") or []:
                ch["last_seen"] = 0
    from widgets import store
    store.save("contactos", db)
    said, text, *_ = WORDS[lang]
    _say(said)
    uid = send_task.commission(WID, "send_to", {"contact": "Raquel Salvador", "text": text, "channel": "whatsapp"}, said)
    assert uid and _asks(world) == [] and len(world["sent"]) == 1


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_bare_reply_that_reaches_nobody_is_a_message_to_the_one_he_named(world, lang, monkeypatch):
    """`reply {text}` with no conversation open reaches nobody: it is his order to write to the person he named."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    said, text, answer, *_ = WORDS[lang]
    from widgets import contract
    monkeypatch.setattr(contract, "would_refuse", lambda *a, **k: {"error": "no_target"})
    _wid, act, payload = send_task_who.readdressed(WID, "reply", {"text": text}, answer)
    assert (act, payload.get("contact")) == ("send_to", "Raquel Jofre")
    monkeypatch.setattr(contract, "would_refuse", lambda *a, **k: None)     # a conversation on screen: it stands
    assert send_task_who.readdressed(WID, "reply", {"text": text}, answer)[1] == "reply"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_our_own_which_question_holds_the_cards_primary_send(world, lang, monkeypatch):
    """The model asked «which Raquel?» in prose: the row it becomes holds `send_to` (the primary act), never the first
    leaving act in alphabetical order (`forward`, with nothing to forward)."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    from nucleo.request import ending, send_task_words
    said = WORDS[lang][0]
    _say(said)
    assert send_task_words.hold(WID, ending.leaving_acts(WID), said, "¿A cuál Raquel?")
    (row,) = _rows()
    assert send_task.artefact(row["id"])["action"] == "send_to"
