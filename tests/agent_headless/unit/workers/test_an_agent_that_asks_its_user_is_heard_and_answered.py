"""An agent of the network that ASKS its user is heard, and only HIS option — with its values — goes back (the class).

Measured before the fix: a skill that answered `422 {"status": "NEEDS_MANDATE", "questions": [...]}` reached the
worker as «the agents did not answer». `nucleo/mesh_dialog` reads a question by SHAPE (never status words); offers
only options he can pick as they stand (one that needs a value of his is not offered); applies his option by the
agent's own contract (a choice's `set`, a question's `field`, or `{id, choice}` for a job — a question with options
never takes words); and keeps the VALUES he picked as his standing answer, applied only when the agent offers exactly
those values again — so an agent cannot redefine what he chose (audit P1-4).

The fixtures are the documented shapes of a network booking agent (trimmed).

Disarm: return [] from `questions_in` → red; match a standing answer by position instead of values → red; keep the
threads in one shared value → red.
"""
from __future__ import annotations

import copy

import pytest

from nucleo import mesh_dialog as d

MANDATE = {"status": "NEEDS_MANDATE", "questions": [
    {"id": "when.exact", "text": "Si no hay mesa a las 21:00, ¿qué otra hora se puede aceptar?",
     "choices": [{"label": "Solo a las 21:00", "set": {"when.exact": True}},
                 {"label": "Otra franja (indica desde y hasta)", "set": {"when.earliest": None, "when.latest": None},
                  "needsValue": "time"},
                 {"label": "Entre las 20:45 y las 21:15", "set": {"when.earliest": "20:45", "when.latest": "21:15"}}]},
    {"id": "constraints.maxPenalty", "text": "¿Cuánto se puede comprometer como señal?",
     "choices": [{"label": "Nada", "set": {"constraints.maxPenalty": 0}},
                 {"label": "Hasta 20", "set": {"constraints.maxPenalty": 20}}]}]}
JOB_ASKS = {"status": "NEEDS_INPUT", "result": {"questions": [
    {"id": "q1", "topic": "time", "ask": "No hay mesa a las 21:00. Ofrecen las 21:30. ¿La aceptas?",
     "choices": [{"id": "accept", "label": "Sí, a las 21:30", "value": "21:30"}, {"id": "decline", "label": "No"}]}]}}
BODY = {"restaurant": {"name": "Casa"}, "date": "2026-11-27", "time": "21:00", "party_size": 2}


@pytest.fixture
def db(tmp_path, monkeypatch):
    from memory import db as memdb
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    import rules
    rules._reset_for_tests()
    yield
    rules._reset_for_tests()


def test_a_question_is_read_by_its_shape_and_offers_only_what_he_can_pick():
    qs = d.questions_in(MANDATE)
    assert [q["id"] for q in qs] == ["when.exact", "constraints.maxPenalty"]
    assert [(c["n"], c["label"]) for c in qs[0]["choices"]] == [(0, "Solo a las 21:00"), (1, "Entre las 20:45 y las 21:15")]
    job = d.questions_in(JOB_ASKS)[0]
    assert job["id"] == "q1" and "21:30" in job["text"]
    a2a = d.questions_in({"status": {"state": "input-required", "message": {"parts": [{"text": "¿Para cuántos?"}]}}})
    assert a2a == [{"id": "input", "text": "¿Para cuántos?", "choices": []}]
    assert d.questions_in({"status": "CONFIRMED", "result": {"confirmed": {"id": "r1"}}}) == []


def test_his_option_is_written_where_the_agent_said_and_nothing_else_is_taken():
    q = d.questions_in(MANDATE)[0]
    body, job, why = d.apply(BODY, q, 1)
    assert not why and job is None and body["when"] == {"earliest": "20:45", "latest": "21:15"} and "when" not in BODY
    assert d.apply(BODY, q, None, "a las ocho")[2]                         # words never answer a question with options
    _b, job, _w = d.apply({}, d.questions_in(JOB_ASKS)[0], 0)
    assert job == {"id": "q1", "choice": "accept"}                         # the option's ID, never its value
    assert d.apply({}, {"id": "input", "text": "?", "choices": []}, None, "cuatro")[2]   # no option: nothing is sent
    body, _j, _w = d.apply({}, {"id": "input", "text": "?", "choices": [], "field": "party_size"}, None, "4")
    assert body == {"party_size": "4"}


def test_his_standing_answer_is_its_values_and_the_agent_cannot_redefine_it(db):
    q = d.questions_in(MANDATE)
    assert d.remember("dining-agent", "book-by-phone", q[1], 0)            # «nada»: maxPenalty 0
    assert not d.remember("dining-agent", "book-by-phone", d.questions_in(JOB_ASKS)[0], 0)   # about that day only
    body, still, applied = d.prefill("dining-agent", "book-by-phone", q, BODY)
    assert body["constraints"] == {"maxPenalty": 0} and [x["id"] for x in still] == ["when.exact"] and len(applied) == 1
    moved = copy.deepcopy(MANDATE)                                         # same position, other value
    moved["questions"][1]["choices"][0]["set"] = {"constraints.maxPenalty": 50}
    body, still, applied = d.prefill("dining-agent", "book-by-phone", d.questions_in(moved), BODY)
    assert not applied and "constraints" not in body and len(still) == 2
    swapped = copy.deepcopy(MANDATE)                                       # his values at another position still apply
    swapped["questions"][1]["choices"].reverse()
    body, _s, applied = d.prefill("dining-agent", "book-by-phone", d.questions_in(swapped), BODY)
    assert body["constraints"] == {"maxPenalty": 0} and applied
    assert not d.prefill("another-agent", "book-by-phone", q, BODY)[2]


def test_each_thread_is_its_own_row_so_two_writers_never_erase_each_other(db):
    a = d.save({"agent": "a", "skill": "s"})
    stale = d.thread(a)                                      # one process holds this copy…
    b = d.save({"agent": "a", "skill": "t", "job": {"id": "j-9"}})   # …while the other writes another thread
    d.save({**stale, "note": "x"})
    assert d.thread(b)["job"]["id"] == "j-9" and {t["id"] for t in d.all_threads()} == {a, b}
    from memory import api as memory
    assert sorted(memory.kv_keys("mesh:thread:")) == sorted(f"mesh:thread:{x}" for x in (a, b))   # one row each
