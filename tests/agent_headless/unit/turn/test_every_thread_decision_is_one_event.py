"""Every thread decision is ONE `thread` event, with the menu it was weighed against (V2-878 §6, node 7.130).

Which errand a request belongs to was decided in four places and seen in one: `flow_of` emitted only its hit, the
model judge emitted nothing, and a request that opened a NEW errand, was only conversation or named several errands
left no trace. These tests hold the evidence: each route is exactly one `decided` event (new · continue · correct ·
close · evict · conversation · list) with its menu; the judge emits its menu and answer, and who asked; a judge that
runs out of the turn's budget is counted; the recall shortcuts say which fired and in which language; a clause that
would stand alone under a cut is measured without splitting anything; the commission's shadow carries the promise.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from memory import db as memdb
from nucleo.turn import brief_turn, flow_of, thread_event, turn_marks
from nucleo.request import append as _append
from voice import observer, trace

_REAL_JUDGE = _append._judge

LIVE = {"en": {"id": "5", "request": "find me a used Toyota 4Runner, thirty to fifty thousand", "sheet": "b1-5"},
        "es": {"id": "5", "request": "búscame un Toyota 4Runner de segunda mano, entre treinta y cincuenta mil",
               "sheet": "b1-5"}}
TABLE = {"en": {"id": "6", "request": "book a table for two in Seville on Friday", "sheet": "b1-6"},
         "es": {"id": "6", "request": "resérvame una mesa para dos en Sevilla el viernes", "sheet": "b1-6"}}
NEW_REQ = {"en": "find me a flat to rent in Madrid, two bedrooms, near Retiro",
           "es": "encuéntrame un piso de alquiler en Madrid, dos habitaciones, cerca del Retiro"}
REFINE = {"en": "the Toyota 4Runner, only diesel, under forty thousand",
          "es": "el Toyota 4Runner, solo diésel, por debajo de cuarenta mil"}
BOTH = {"en": "The Toyota 4Runner under forty thousand. And the table in Seville, make it at nine.",
        "es": "El Toyota 4Runner por debajo de cuarenta mil. Y la mesa en Sevilla, que sea a las nueve."}


@pytest.fixture
def door(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    memdb.reset_db()
    flow_of._TURN.clear()
    flow_of._NOT_MINE.clear()
    turn_marks.reset()
    thread_event.reset()
    state = {"pool": [], "judge": "", "stop": None, "events": []}
    monkeypatch.setattr(flow_of, "candidates", lambda: list(state["pool"]))
    monkeypatch.setattr("nucleo.request.append._judge", lambda text, live: (state["judge"], "about" if state["judge"]
                                                                            else "separate"))
    monkeypatch.setattr("nucleo.request.stop.verdict", lambda brief: state["stop"])
    real = observer.emit

    def emit(kind, label, *a, **k):
        state["events"].append((kind, label, k.get("extra") or {}))
        return real(kind, label, *a, **k)
    monkeypatch.setattr(observer, "emit", emit)
    yield state
    flow_of._TURN.clear()
    turn_marks.reset()
    trace.adopt("")
    memdb.reset_db()


def _route(t: str, text: str) -> dict:
    trace.adopt(t)
    brief_turn.remember_for_the_turn({"judged": text})
    return asyncio.run(flow_of.route(text))


def _thread(state, event: str) -> list[dict]:
    return [x for k, _l, x in state["events"] if k == thread_event.KIND and x.get("event") == event]


def test_thread_is_a_worker_family_kind():
    assert observer._CAT[thread_event.KIND] == "worker"


@pytest.mark.parametrize("lang", ["en", "es"])
def test_a_new_request_is_one_decided_event_with_its_menu(door, lang):
    door["pool"] = [dict(LIVE[lang])]
    r = _route("T1", NEW_REQ[lang])
    assert r["as"] == flow_of.NEW
    ev = _thread(door, "decided")
    assert len(ev) == 1, f"one decision, {len(ev)} events"
    assert ev[0]["verb"] == thread_event.NEW and ev[0]["menu"] == ["5"] and ev[0]["window_had_commission"] is True
    assert ev[0]["heard"] and ev[0]["by"] == "model"


@pytest.mark.parametrize("lang", ["en", "es"])
def test_a_refinement_continues_its_errand_and_the_judge_says_its_menu_and_answer(door, lang):
    door["pool"], door["judge"] = [dict(LIVE[lang]), dict(TABLE[lang])], "5"
    r = _route("T2", REFINE[lang])
    assert r["as"] == flow_of.INJECT and r["flow"] == "5"
    (ev,) = _thread(door, "decided")
    assert ev["verb"] == thread_event.CONTINUE and ev["id"] == "5" and ev["menu"] == ["5", "6"]
    judged = _thread(door, "judged")
    if ev["by"] == "model":
        assert judged and judged[0]["answer"] == "5" and judged[0]["caller"] == "flow_of"
        assert [m["id"] for m in judged[0]["menu"]] == ["5", "6"]
    else:
        assert ev["by"] == "containment" and not judged


@pytest.mark.parametrize("stop, verb", [("steer", thread_event.CORRECT), ("stop", thread_event.CLOSE)])
def test_a_steer_is_a_correction_and_a_stop_a_close(door, stop, verb):
    door["pool"], door["judge"], door["stop"] = [dict(LIVE["en"])], "5", stop
    _route("T3", "the Toyota 4Runner — " + ("look on coches.net instead" if stop == "steer" else "stop it"))
    (ev,) = _thread(door, "decided")
    assert ev["verb"] == verb and ev["as"] == stop


@pytest.mark.parametrize("lang, said", [("en", "Okay."), ("es", "Vale.")])
def test_chat_no_flow_claims_is_conversation_and_two_errands_are_a_list(door, monkeypatch, lang, said):
    from nucleo.turn import brief as tb
    door["pool"] = [dict(LIVE[lang]), dict(TABLE[lang])]
    _route("T5", BOTH[lang])
    monkeypatch.setattr(tb, "read", lambda h, key, d="", min_confidence=None:      # the paid verdict: a comment
                        ("comment", {"confidence": 0.93, "used": True}) if key == tb.REQUEST_KEY else (d, None))
    _route("T4", said)
    ev = _thread(door, "decided")
    assert [e["verb"] for e in ev] == [thread_event.LIST, thread_event.CONVERSATION]
    assert {p["id"] for p in ev[0]["parts"]} == {"5", "6"} and ev[1]["by"] == "verdict"


def test_words_a_worker_hands_back_are_an_eviction(door):
    flow_of.not_mine("and the insurance — get me quotes", "5")
    (ev,) = _thread(door, "decided")
    assert ev["verb"] == thread_event.EVICT and ev["id"] == "5" and ev["by"] == "handed_back"


def test_a_judge_past_the_turns_budget_is_counted(door, monkeypatch):
    door["pool"] = [dict(LIVE["en"])]
    monkeypatch.setattr(flow_of, "JUDGE_S", 0.05)
    monkeypatch.setattr("nucleo.request.append._judge", lambda text, live: time.sleep(0.3) or ("5", "about"))
    r = _route("T6", "anything new yet?")
    assert r["as"] == flow_of.NEW
    (to,) = _thread(door, "judge_timeout")
    assert to["menu"] == ["5"] and to["caller"] == "flow_of" and to["budget_s"] == 0.05
    assert thread_event.counts()["judge_timeout"] == 1


def test_the_dispatchers_judge_names_itself_and_an_unreadable_answer(door, monkeypatch):
    from nucleo.memory_agent.processor import llm
    from nucleo.request import append
    monkeypatch.setattr(append, "_judge", _REAL_JUDGE)
    monkeypatch.setattr(llm, "chat_sync", lambda *a, **k: "I think it is about the car")
    assert append.about_a_live_errand("how is it going?", [("t1", "find a car")]) == ""
    (j,) = _thread(door, "judged")
    assert j["caller"] == "dispatch" and j["outcome"] == "unreadable" and j["menu"] == [{"id": "t1", "goal": "find a car"}]


@pytest.mark.parametrize("lang", ["en", "es"])
def test_a_recall_shortcut_says_which_fired_and_the_language(door, monkeypatch, lang):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    thread_event.recall_fired("what were we talking about?", recall=False, recent=True)
    assert thread_event.recall_fired("hello", recall=False, recent=False) is None
    (ev,) = _thread(door, "recall")
    assert ev["needs_recent"] is True and ev["needs_recall"] is False and ev["lang"] == lang


def test_a_clause_with_words_of_its_own_is_measured_not_split(door):
    pool = [dict(LIVE["es"])]
    door["pool"] = pool
    text = "del Toyota 4Runner con eso basta, y reserva un vuelo a Roma"
    r = _route("T7", text)
    assert r["as"] != flow_of.LIST, "measuring must not change the route"
    (ws,) = _thread(door, "would_split")
    assert ws["clauses"][0]["rides_with"] == "5" and "Roma" in ws["clauses"][0]["clause"]


def test_the_commission_shadow_carries_the_promise(monkeypatch):
    from nucleo.turn import commission
    monkeypatch.setattr(commission, "_answer", lambda brief, key: ("show", 0.6) if key == "screen_action" else ("", 0.0))
    out = commission.shadow(lambda *a, **k: None, at="close", brief={}, escalate_req={}, model_calls=(),
                            words_said=True)
    assert out["promise"] == {"screen_action": "show", "confidence": 0.6, "called": False, "wrote": True}
    assert {"would", "did", "changes", "would_b", "changes_b", "model_calls"} <= set(out), "the shadow lost a field"
