"""V2-931 · ONE live confirmation question per act, and one record line when he answers it — for ANY act that asks.

His test of 2026-11-18: two unanswered «shall I send it?» for the same message sat in the conversation, the first one
stale after he corrected the text; and an answered question simply vanished. Now a question whose terms changed is
SUPERSEDED (said on the timeline, its id refused by the answer door, its card replaced), and his yes or no leaves ONE
line of record — «<his name> confirms …» — that the wall keeps in its place, in the system's colour.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo.circuit import ask_trace, asker


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    events = []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None:
                        events.append({"kind": kind, "label": label, "text": text, **(extra or {})}))
    yield events
    memdb.reset_db()


def _ask(uid: str, ask_id: str, question: str, payload: dict) -> dict:
    entry = {"ask_id": ask_id, "corr_id": ask_id, "uid": uid, "question": question, "action": "widget_data",
             "retained": {"action": "widget_data", "payload": payload}, "options": ["Sí", "No"]}
    asker.ask(uid, entry)
    return entry


def _row(uid: str) -> None:
    ts.task_put({"id": uid, "goal": "g", "title": "t", "state": "running", "created_at": int(time.time())})


def test_the_terms_are_the_questions_identity():
    one = {"retained": {"action": "widget_data", "payload": {"widget_id": "ficheros", "action": "delete", "payload": {"files": ["a.pdf"]}}}}
    three = {"retained": {"action": "widget_data", "payload": {"widget_id": "ficheros", "action": "delete",
                                                               "payload": {"files": ["a.pdf", "b.pdf", "c.pdf"]}}}}
    assert ask_trace.terms_of(one) and ask_trace.terms_of(one) != ask_trace.terms_of(three), "1 file and 3 files are two questions"
    assert ask_trace.terms_of(one) == ask_trace.terms_of({"retained": dict(one["retained"])})
    assert ask_trace.terms_of({"question": "which one?"}) == ""


@pytest.mark.parametrize("before,after", [
    ({"widget_id": "mensajeria", "action": "send_draft", "payload": {"contact": "Quinn", "text": "dormidita"}},
     {"widget_id": "mensajeria", "action": "send_draft", "payload": {"contact": "Quinn", "text": "espero que estés dormidita"}}),
    ({"widget_id": "ficheros", "action": "delete", "payload": {"files": ["a.pdf"]}},
     {"widget_id": "ficheros", "action": "delete", "payload": {"files": ["a.pdf", "b.pdf", "c.pdf"]}}),
], ids=["a send whose text changed", "delete 1 file → delete 3 files"])
def test_a_question_whose_terms_changed_supersedes_the_one_before_and_voids_its_yes(world, before, after):
    from nucleo.cli import worker_api_answer
    _row("q1")
    _ask("q1", "q1-a", "Shall I?", before)
    _ask("q1", "q1-b", "Shall I, as it is now?", after)
    (ev,) = [e for e in world if e["kind"] == ask_trace.EV]
    assert (ev["ask_id"], ev["by"], ev["outcome"]) == ("q1-a", "q1-b", "superseded") and ev["terms"] != ev["new_terms"]
    assert "terms changed" in ev["label"]
    assert worker_api_answer.refusal("q1-a") == worker_api_answer.CLOSED, "a yes can still reach the question that was replaced"
    assert worker_api_answer.refusal("q1-b") == "" and asker.artefact("q1")["ask_id"] == "q1-b"
    assert ts.task_get("q1")["ask_id"] == "q1-b", "the row carries two questions"


def test_the_same_question_told_again_supersedes_nothing(world):
    _row("q2")
    e = _ask("q2", "q2-a", "Shall I?", {"widget_id": "notas", "action": "delete", "payload": {"id": 1}})
    asker.ask("q2", e)
    assert [x for x in world if x["kind"] == ask_trace.EV] == []


@pytest.mark.parametrize("lang,name,said,line", [
    ("es", "Ricard Fabra", "yes", "Ricard lo confirma."), ("es", "", "no", "El operador no lo confirma."),
    ("en", "Quinn Ferrer", "yes", "Quinn confirms it."), ("en", "", "no", "The operator does not confirm it."),
])
def test_his_answer_leaves_one_record_line_with_his_name(world, monkeypatch, lang, name, said, line):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    from memory import api as memory
    monkeypatch.setattr(memory, "state", lambda: {"operator_name": name})
    entry = {"ask_id": "q3-a", "uid": "q3", "question": "The message for Odile is ready — shall I send it?",
             "retained": {"action": "widget_data", "payload": {}}}
    assert asyncio.run(ask_trace.resolved("q3", entry, said)) == line      # the suite's wording is offline: the plain line
    (ev,) = [e for e in world if e["kind"] == ask_trace.EV]
    assert (ev["text"], ev["outcome"], ev["task_id"], ev["ask_id"]) == (line, said, "q3", "q3-a")


def test_the_line_is_worded_from_the_fact_as_a_record_not_as_speech(world, monkeypatch):
    from memory import api as memory
    from nucleo import wording
    seen = []
    monkeypatch.setattr(memory, "state", lambda: {"operator_name": "Ricard"})
    monkeypatch.setattr(wording, "_ask", lambda system, user, seat: seen.append((system, user)) or "Ricard confirma que mandemos el mensaje a Odile")
    entry = {"ask_id": "q4-a", "uid": "q4", "question": "El mensaje para Odile está listo, ¿se lo mando?", "retained": {"action": "x"}}
    assert asyncio.run(ask_trace.resolved("q4", entry, "yes")) == "Ricard confirma que mandemos el mensaje a Odile"
    system, user = seen[0]
    assert "RECORD" in system and "third person" in system and "Ricard CONFIRMED" in user and "¿se lo mando?" in user


def test_only_a_yes_or_a_no_to_a_consent_question_leaves_a_line(monkeypatch):
    left = []
    monkeypatch.setattr(ask_trace, "resolved_soon", lambda uid, entry, said: left.append((uid, said)))
    decision = lambda q, text, choice, options: {0: "yes", 1: "no"}.get(choice)     # noqa: E731

    async def took(corr_id, text, **kw):
        return True

    async def refused(corr_id, text, **kw):
        return False
    consent = {"uid": "q5", "ask_id": "q5-a", "question": "Shall I?", "action": "widget_data", "retained": {"action": "widget_data"}}
    clarify = {"uid": "q6", "ask_id": "q6-a", "question": "Which one?", "action": "ask_user"}
    run = lambda *a, **k: asyncio.run(ask_trace.answered(*a, **k))                   # noqa: E731
    assert run(took, consent, decision, "q5-a", "sí", choice=0) and run(took, consent, decision, "q5-a", "no", choice=1)
    assert run(took, consent, decision, "q5-a", "mejor mañana", choice=None)        # neither: the worker reads it
    assert run(took, clarify, decision, "q6-a", "el segundo", choice=0)             # a clarification is dialogue
    assert run(refused, consent, decision, "q5-a", "sí", choice=0) is False         # an answer nobody took
    assert left == [("q5", "yes"), ("q5", "no")]


def test_the_wall_paints_the_record_line_as_a_system_row_and_the_answer_door_is_wrapped():
    root = Path(__file__).resolve().parents[3]
    sse = (root / "frontend" / "app" / "services" / "sse.js").read_text("utf-8")
    # The wall moved out of the store (the wall plan, commit 3/5): the old path writes it through `wall-legacy.js`.
    assert 'd.kind === "ask_resolved"' in sse and 'legacy.pushChat({ role: "record", text: d.text })' in sse
    legacy = (root / "frontend" / "app" / "services" / "wall-legacy.js").read_text("utf-8")
    assert 'NOTE_ROLES = new Set(["sys", "record", "peer"])' in legacy, "a record is no longer a note of its own kind"
    wall = (root / "frontend" / "app" / "components" / "ChatWall.js").read_text("utf-8")
    assert '(l.kind === "record" ? "record"' in wall, "the desktop wall no longer classes a record note as `record`"
    css = (root / "frontend" / "app" / "core" / "shared-surfaces.css").read_text("utf-8")
    assert ".cw-msg.record,.zm-msg.record{" in css, "the record line has no colour of its own in one of the two shells"
    from voice import observer
    import inspect
    assert '"ask_resolved"' in inspect.getsource(observer)
    from nucleo.cli import worker_api_answer
    assert "ask_trace" in inspect.getsource(worker_api_answer.answer) and "ask_trace.superseded" in inspect.getsource(asker.ask)
