"""A complete leaving call runs on its row with no question and no worker; what lacks is what the act DECLARES (V2-919).

Measured 2026-11-16: the model's `mensajeria:create_group` call carried `{name, platform, members: [<person>]}` and the
hand-off asked the send's question about a recipient (the list read as empty) and bound his answer to a worker. Now:

  · the complete call (a list of people he named, a name, a channel) is retained with nothing missing and handed to
    its run — zero questions, zero workers, one row (es, en; one person and two);
  · a field the action declares optional (`text` of a group) is never asked;
  · the list arriving in his ANSWER fills that field on the SAME row, as an item the card splits, and the row runs;
    so does the answering turn's own call carrying the list;
  · another declared field that lacks (the channel) is asked by its declared label on the same row, never handed to
    a worker; his answer fills it and the row runs.

Disarmed (seen red): `send_task.required` back to the send's rules → the optional text is asked; `_go_on` back to the
worker → the second field opens a worker.
"""
from __future__ import annotations

import pytest

from memory import db as memdb, embeddings as mememb, tasks_store as ts
from nucleo import his_words, untrusted
from nucleo.circuit import asker
from nucleo.request import inline_ask, model, send_task, send_task_answer

WID, ACT = "mensajeria", "create_group"
WORDS = {
    "es": {"one": ("crea un grupo de WhatsApp con Ana Prat que se llame Cena", ["Ana Prat"], "Cena"),
           "two": ("crea un grupo con Ana Prat y Luis Gil llamado Viaje en WhatsApp", ["Ana Prat", "Luis Gil"], "Viaje"),
           "bare": "crea un grupo de WhatsApp que se llame Cena", "who": "con Ana Prat y Luis Gil",
           "nochan": "crea un grupo con Ana Prat que se llame Cena"},
    "en": {"one": ("make a WhatsApp group with Ana Prat called Dinner", ["Ana Prat"], "Dinner"),
           "two": ("create a group called Trip with Ana Prat and Luis Gil on WhatsApp", ["Ana Prat", "Luis Gil"], "Trip"),
           "bare": "make a WhatsApp group called Dinner", "who": "with Ana Prat and Luis Gil",
           "nochan": "make a group with Ana Prat called Dinner"},
}
READING = {"result": {"message_channel": {"choice": "whatsapp", "confidence": 0.97}}, "open_ids": [WID]}


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
    ran, events = [], []
    monkeypatch.setattr(send_task, "_schedule", lambda uid: ran.append(uid))
    import nucleo.request.send_task_answer as sta
    monkeypatch.setattr(sta, "_schedule", lambda uid: ran.append(uid))
    from nucleo.acts import errand
    monkeypatch.setattr(errand, "escalate_to_slowbrain",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("a worker was started")))
    import voice.observer as _obs
    real = _obs.emit
    monkeypatch.setattr(_obs, "emit", lambda kind, label, text="", role="", extra=None, **kw:
                        events.append({"kind": kind, "label": label, **(extra or {})})
                        or real(kind, label, text=text, role=role, extra=extra))
    yield {"ran": ran, "events": events}
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


def _rows():
    return ts.tasks_where(states=("waiting", "running", "done", "failed", "cancelled"), visible_only=False)


def _asks(world):
    return [e for e in world["events"] if e["kind"] == "ask"]


@pytest.mark.parametrize("lang", ["es", "en"])
@pytest.mark.parametrize("which", ["one", "two"])
def test_a_complete_call_runs_with_no_question_and_no_worker(world, lang, which, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    said, members, name = WORDS[lang][which]
    _say(said)
    uid = send_task.commission(WID, ACT, {"name": name, "platform": "whatsapp", "members": members}, said,
                               reading=READING)
    assert uid and world["ran"] == [uid], "the row that was born is the row that runs"
    assert _asks(world) == [], "nothing lacks: the list is his people, the optional text is not asked"
    art = send_task.artefact(uid)
    assert art["slots"]["recipient"]["source"] == "his" and send_task.missing(art) == ("", "")
    assert len(_rows()) == 1


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_list_in_his_answer_fills_the_row_that_waited(world, lang, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    w = WORDS[lang]
    _say(w["bare"])
    uid = send_task.commission(WID, ACT, {"name": "Cena", "platform": "whatsapp"}, w["bare"], reading=READING)
    assert world["ran"] == [] and len(_asks(world)) == 1 and _asks(world)[0]["task_id"] == uid
    entry = asker.artefact(uid)
    assert entry["retained"]["slot"] == "members"
    _say(w["who"])
    got = send_task_answer.answered(uid, entry, w["who"])
    assert got["ok"] and "worker" not in got and world["ran"] == [uid]
    assert send_task.artefact(uid)["payload"]["members"] == [w["who"]], "his answer is an item of the list field"
    assert len(_rows()) == 1, "the same row, no second task"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_answering_turns_call_with_the_list_fills_the_row(world, lang, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    w = WORDS[lang]
    _say(w["bare"])
    uid = send_task.commission(WID, ACT, {"name": "Cena", "platform": "whatsapp"}, w["bare"], reading=READING)
    _say(w["who"])
    assert send_task_answer.take_call(WID, ACT, {"name": "Cena", "platform": "whatsapp",
                                                 "members": ["Ana Prat", "Luis Gil"]}, w["who"]) == uid
    assert world["ran"] == [uid] and len(_rows()) == 1
    assert send_task.artefact(uid)["payload"]["members"] == ["Ana Prat", "Luis Gil"]


@pytest.mark.parametrize("lang", ["es", "en"])
def test_another_declared_field_is_asked_by_its_label_on_the_same_row(world, lang, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    w = WORDS[lang]
    _say(w["nochan"])
    uid = send_task.commission(WID, ACT, {"name": "Cena", "members": ["Ana Prat"]}, w["nochan"])
    asks = _asks(world)
    assert world["ran"] == [] and len(asks) == 1
    from i18n import langs
    from nucleo.flash import payload_fill
    label = payload_fill._payload_spec(WID, ACT)["platform"]
    assert asks[0]["text"] == langs.spec(lang).send_missing_field.format(field=label, who="Ana Prat")
    entry = asker.artefact(uid)
    assert entry["retained"]["slot"] == "platform"
    got = send_task_answer.answered(uid, entry, "whatsapp")
    assert got["ok"] and "worker" not in got and world["ran"] == [uid] and len(_rows()) == 1


def test_a_second_field_that_lacks_after_an_answer_is_asked_not_composed(world, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    said = "make a group called Dinner"
    _say(said)
    uid = send_task.commission(WID, ACT, {"name": "Dinner"}, said)
    first = asker.artefact(uid)
    assert first["retained"]["slot"] == "members"
    got = send_task_answer.answered(uid, first, "Ana Prat")
    assert got.get("asked") and "worker" not in got and world["ran"] == []
    assert asker.artefact(uid)["retained"]["slot"] == "platform", "the next declared field, on the same row"
    assert len(_rows()) == 1
