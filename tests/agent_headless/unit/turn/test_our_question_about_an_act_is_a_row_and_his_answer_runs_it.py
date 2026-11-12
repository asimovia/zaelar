"""Our own question about an act of a card is a ROW, and his answer runs the act on it (group A5, 2026-11-12; ES/EN).

Measured on the kindergarten bench (`si-es` 1/3): «apúntame el gimnasio» → the model asked «¿a qué hora?» without
calling, and «¿qué tengo mañana?» → «…¿te apunto el gimnasio?» → «sí». The question was ours and it was not a row:
`ask_outside_door.measure` made durable only a question about acts that LEAVE, so his «a las siete» or his «sí» worked
only if the model happened to call `add_meeting` on the next turn — and the `readable` hold, read at the licence, ate
the model's words when it did not. Now a turn that ends asking while the brief names a declared act at the act floor
makes its row wait with his request (`utterance`); his answer binds to it and `answered_offer.run` composes the act's
payload by one bounded pass (the kept fallback) and runs it through the card's door on THAT row; a declared no cancels
it; the answering turn's own call of the act is the same answer. Disarm: no row (the act not named) → his answer has
nowhere to go and nothing runs.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from memory import db as memdb, embeddings as mememb, tasks_store as ts
from nucleo import his_words, untrusted
from nucleo.circuit import asker
from nucleo.request import answered_offer, ask_outside_door as aod, consent_ask, inline_ask, model

WID, ACT = "agenda", "add_meeting"
_REAL_COMPOSE = answered_offer.compose          # taken before the fixture mocks it
WORDS = {
    "es": {"said": "Apúntame el gimnasio mañana", "q": "Vale. ¿A qué hora?", "answer": "A las siete",
           "offer_q": "Mañana tienes libre a las siete. ¿Te apunto el gimnasio?", "yes": "Sí, por favor"},
    "en": {"said": "Put the gym in my calendar tomorrow", "q": "Sure. What time?", "answer": "At seven",
           "offer_q": "Tomorrow you are free at seven. Shall I add the gym?", "yes": "Yes please"},
}
PAYLOAD = {"title": "Gimnasio", "date": "2026-11-13", "startTime": "19:00", "endTime": "20:00"}


def _brief(target=f"{WID}:{ACT}", conf=0.9) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": [WID],
            "result": {"screen_action": {"choice": target, "confidence": conf},
                       "request_type": {"choice": "order", "confidence": 0.9}}}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    untrusted.reset()
    his_words.reset()
    inline_ask._RECENT.clear()
    inline_ask._TAKEN.clear()
    inline_ask._RESUMING.clear()
    sent, events, composed = [], [], []

    async def _dispatch(wid, action, payload, *, row="", text="", **kw):
        sent.append({"widget": wid, "action": action, "payload": dict(payload), "row": row, "text": text})
        return {"ok": True, "row": row}

    async def _compose(wid, act, *, request, question, answer, spec=None):
        composed.append({"widget": wid, "act": act, "request": request, "question": question, "answer": answer})
        return dict(PAYLOAD)
    from nucleo.flash import data_ops
    monkeypatch.setattr(data_ops, "dispatch_and_report", _dispatch)
    monkeypatch.setattr(answered_offer, "compose", _compose)
    from nucleo.acts import errand
    monkeypatch.setattr(errand, "escalate_to_slowbrain",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("a worker was started for an app act")))
    import voice.observer as _obs
    monkeypatch.setattr(_obs, "emit", lambda kind, label, text="", role="", extra=None, **kw:
                        events.append({"kind": kind, "label": label, "text": text, **(extra or {})}))
    yield {"sent": sent, "events": events, "composed": composed}
    model._TURN.set(None)
    inline_ask._RESUMING.clear()
    inline_ask._TAKEN.clear()
    untrusted.reset()
    his_words.reset()
    memdb.reset_db()
    mememb.reset()


def _rows():
    return ts.tasks_where(states=("waiting", "running", "done", "failed", "cancelled"), visible_only=False)


def _ask(w, question_key="q"):
    """His turn ends on OUR question about the act the brief named: the row waits."""
    model._TURN.set(None)
    model.begin(w["said"], trace="t-1")
    his_words.note(w["said"])
    measured = aod.measure(_brief(), w[question_key], did_act=False)
    assert measured and measured["widget"] == WID and measured["actions"] == [ACT] and measured["leaves"] == []
    ask_id = aod.held(measured, w[question_key], w["said"])
    (row,) = [r for r in _rows() if r["state"] == "waiting"]
    assert ask_id and row["state"] == "waiting" and row["ask_id"] == ask_id and row["ask"] == w[question_key]
    return row["id"], dict(asker.artefact(row["id"]), state="pending")


@pytest.mark.parametrize("lang", ["es", "en"])
def test_his_fact_answers_our_question_and_the_act_runs_on_that_row(world, lang):
    w = WORDS[lang]
    uid, entry = _ask(w)
    ret = entry["retained"]
    assert (ret["kind"], ret["widget"], ret["actions"], ret["text"]) == ("utterance", WID, [ACT], w["said"])
    assert entry["consent"] == "ask_fact" and entry["said"] is True
    res = asyncio.run(inline_ask.rerun(uid, entry, w["answer"]))
    assert res and res.get("ok")
    (c,) = world["composed"]
    assert (c["widget"], c["act"], c["request"], c["question"], c["answer"]) == (WID, ACT, w["said"], w["q"], w["answer"])
    (s,) = world["sent"]
    assert (s["widget"], s["action"], s["payload"], s["row"], s["text"]) == (WID, ACT, PAYLOAD, uid, w["said"])


@pytest.mark.parametrize("lang", ["es", "en"])
def test_his_yes_to_our_offer_runs_the_act_and_his_no_cancels_the_row(world, lang):
    w = WORDS[lang]
    uid, entry = _ask(w, "offer_q")
    asyncio.run(inline_ask.rerun(uid, entry, w["yes"]))
    (s,) = world["sent"]
    assert (s["action"], s["row"]) == (ACT, uid)
    world["sent"].clear()
    uid2, entry2 = _ask(w, "offer_q")
    assert uid2 != uid
    res = asyncio.run(inline_ask.rerun(uid2, entry2, consent_ask.yes_no()[1]))
    assert res == {"ok": False, "row": uid2} and world["sent"] == []
    assert ts.task_get(uid2)["state"] == "cancelled"


def test_the_answering_turns_own_call_is_the_same_answer_and_runs_once(world):
    w = WORDS["es"]
    uid, entry = _ask(w)
    model._TURN.set(None)
    model.begin(w["answer"], trace="t-2")
    assert inline_ask.claim(WID, ACT, dict(PAYLOAD)) == (uid, False), "the model's call answers the waiting row"
    assert asyncio.run(inline_ask.rerun(uid, entry, w["answer"])) is None, "the bound answer runs nothing twice"
    assert world["composed"] == [] and world["sent"] == []
    assert inline_ask.claim("musica", "play", {"query": "x"}) == ("", False), "another card's act is nobody's answer"


def test_a_pass_that_makes_no_call_leaves_the_row_failed_never_a_guess(world, monkeypatch):
    async def _nothing(wid, act, **kw):
        return None
    monkeypatch.setattr(answered_offer, "compose", _nothing)
    w = WORDS["en"]
    uid, entry = _ask(w)
    res = asyncio.run(inline_ask.rerun(uid, entry, w["answer"]))
    assert res == {"ok": False, "row": uid} and world["sent"] == []
    assert ts.task_get(uid)["state"] == "failed"


def test_the_pass_reads_the_cards_declared_act_and_takes_only_that_call(world, monkeypatch):
    from nucleo.acts import card_pass
    seen = {}

    class _Client:
        async def complete(self, messages, *, spec=None, max_tokens=None, tools=None, no_thinking=False,
                           on_tool_call=None, **kw):
            seen.update(system=messages[0]["content"], tools=[t["function"]["name"] for t in tools])
            on_tool_call("widget_data", {"widget_id": "musica", "action": "play", "payload": {"query": "x"}})
            on_tool_call("widget_data", {"widget_id": WID, "action": ACT, "payload": dict(PAYLOAD)})
    import nucleo.llm.fast_client as fc
    monkeypatch.setattr(fc, "FastClient", _Client)
    monkeypatch.setattr(card_pass, "widget_data_tool", lambda: {"function": {"name": "widget_data"}})
    w = WORDS["es"]
    got = asyncio.run(_REAL_COMPOSE(WID, ACT, request=w["said"], question=w["q"], answer=w["answer"]))
    assert got == PAYLOAD, "only the call of the act the question was about, on its card"
    assert seen["tools"] == ["widget_data"] and w["q"] in seen["system"] and w["answer"] in seen["system"]
    assert "add_meeting" in seen["system"], "the card's declared actions ride along"
    assert asyncio.run(_REAL_COMPOSE(WID, "no_such_act", request="x", question="y", answer="z")) is None


def test_a_question_about_an_act_the_brief_does_not_name_is_no_row(world):
    w = WORDS["es"]
    model.begin(w["said"], trace="t-1")
    assert aod.measure(_brief(conf=0.55), w["q"], did_act=False) is False, "below the act floor: not named"
    assert aod.measure(_brief(target="agenda:no_such_act"), w["q"], did_act=False) is False, "not declared"
    assert aod.measure(_brief(), "Lo apunto.", did_act=False) is False, "the turn did not ask"
    assert _rows() == []


def test_disarmed_without_the_row_his_answer_has_nowhere_to_go(world, monkeypatch):
    monkeypatch.setattr(aod, "named_act", lambda brief: ("", ""))
    w = WORDS["es"]
    model.begin(w["said"], trace="t-1")
    assert aod.measure(_brief(), w["q"], did_act=False) is False
    assert _rows() == []
    from nucleo.cli import worker_api
    assert worker_api.open_asks() == [], "nothing waits: his «a las siete» binds to nothing and nothing runs"
    assert world["sent"] == []
