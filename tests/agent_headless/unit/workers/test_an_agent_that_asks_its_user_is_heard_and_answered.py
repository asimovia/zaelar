"""An agent of the network that ASKS its user something is heard, and his answer goes back to it (the class).

Measured before the fix: a skill that answered `422 {"status": "NEEDS_MANDATE", "questions": [...]}` reached the
worker as «the agents did not answer» — the error reader only knew `need`/`error`/`detail` keys, and a `questions`
list matched none. The same shape arrives as a `200` (a venue that needs a decision) and, from a job, minutes later.
`nucleo/mesh_dialog` reads it by SHAPE (never by status words), applies his answer by the agent's own contract (a
choice's `set` of dotted paths, a question's `field`, or `{id, choice}` for a job), and keeps a fully specified choice
as HIS standing preference — applied only when the same question comes back in the same shape.

The fixture is the real contract, trimmed: two of the eleven questions a live dry-run returned on 2026-11-12.

Disarm: return [] from `questions_in` → red; drop the shape check in `prefill` → red.
"""
from __future__ import annotations

import copy

import pytest

from nucleo import mesh_dialog as d

MANDATE = {"status": "NEEDS_MANDATE", "questions": [
    {"id": "when.exact", "text": "Si no hay mesa a las 21:00, ¿qué otra hora se puede aceptar?",
     "choices": [{"label": "Solo a las 21:00", "set": {"when.exact": True}},
                 {"label": "Entre las 20:45 y las 21:15", "set": {"when.earliest": "20:45", "when.latest": "21:15"}},
                 {"label": "Otra franja (indica desde y hasta)", "set": {"when.earliest": None, "when.latest": None},
                  "needsValue": "time"}],
     "default_suggestion": {"label": "±15 min: 20:45–21:15", "set": {"when.earliest": "20:45"}}},
    {"id": "seating.any", "text": "¿Hay alguna mesa imprescindible?",
     "choices": [{"label": "Cualquier mesa vale", "set": {"seating.any": True}},
                 {"label": "Sí (indica cuáles)", "set": {"seating.must": None}, "needsValue": "seating"}]}]}
JOB_ASKS = {"jobId": "j1", "status": "NEEDS_INPUT",
            "result": {"questions": [{"id": "q1", "text": "No hay a las 21:00; ¿os vale a las 21:30?",
                                      "choices": ["accept", "decline"]}], "answerBy": "2026-11-27T19:00:00Z"}}
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


def test_a_question_is_read_by_its_shape_wherever_it_sits():
    qs = d.questions_in(MANDATE)
    assert [q["id"] for q in qs] == ["when.exact", "seating.any"]
    assert qs[0]["choices"][2]["needs_value"] == "time" and qs[0]["suggestion"].startswith("±15")
    job = d.questions_in(JOB_ASKS)
    assert job[0]["id"] == "q1" and [c["label"] for c in job[0]["choices"]] == ["accept", "decline"]
    a2a = d.questions_in({"id": "t1", "status": {"state": "input-required",
                                                 "message": {"parts": [{"text": "¿Para cuántos?"}]}}})
    assert a2a and a2a[0]["free_text"] and "cuántos" in a2a[0]["text"]
    assert d.questions_in({"status": "CONFIRMED_API", "result": {"confirmed": {"id": "r1"}}}) == []


def test_his_choice_is_written_where_the_agent_said():
    q = d.questions_in(MANDATE)[0]
    body, job, why = d.apply(BODY, q, 1)
    assert not why and job is None
    assert body["when"] == {"earliest": "20:45", "latest": "21:15"} and BODY.get("when") is None   # copy, not mutate
    body, _j, why = d.apply(BODY, q, 2)
    assert body is None and "needs a value" in why                         # a hole is never filled with a guess
    body, _j, _w = d.apply(BODY, q, 2, ["20:00", "22:00"])
    assert body["when"] == {"earliest": "20:00", "latest": "22:00"}
    _b, job, _w = d.apply({}, d.questions_in(JOB_ASKS)[0], 0)
    assert job == {"id": "q1", "choice": "accept"}


def test_a_standing_answer_is_his_and_applies_only_to_the_same_shape(db):
    q = d.questions_in(MANDATE)
    assert d.remember("tablescout", "book-by-phone", q[1], 0)               # «any table» stands
    assert not d.remember("tablescout", "book-by-phone", q[0], 2)           # needs a value: never kept
    assert not d.remember("tablescout", "book-by-phone", d.questions_in(JOB_ASKS)[0], 0)   # about that day only
    body, still, applied = d.prefill("tablescout", "book-by-phone", q, BODY)
    assert body["seating"] == {"any": True} and [x["id"] for x in still] == ["when.exact"] and len(applied) == 1
    reshaped = copy.deepcopy(MANDATE)
    reshaped["questions"][1]["choices"][0]["set"] = {"seating.must": ["terrace"]}
    _b, still, applied = d.prefill("tablescout", "book-by-phone", d.questions_in(reshaped), BODY)
    assert not applied and len(still) == 2                                  # another shape: asked again
    _b, still, applied = d.prefill("another-agent", "book-by-phone", q, BODY)
    assert not applied                                                      # his answer was to THAT agent


def test_a_thread_binds_a_job_by_its_id(db):
    tid = d.save({"agent": "a", "skill": "s", "job": {"id": "j-9"}})
    assert d.thread(tid)["agent"] == "a" and d.with_job("j-9")["id"] == tid
    assert [t["id"] for t in d.open_jobs()] == [tid]
    d.save({**d.thread(tid), "job": {"id": "j-9", "done": True}})
    assert d.open_jobs() == []
