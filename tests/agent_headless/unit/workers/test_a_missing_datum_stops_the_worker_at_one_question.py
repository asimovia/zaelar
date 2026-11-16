"""A card that refuses a worker's act for a datum only he can give holds the row at ONE question (mechanism).

Measured: a worker whose card refused its act for a missing name went on to ~20 chained searches for more than 15
minutes. Now the refusal names the datum and the bridge holds the row: only the question to him (which parks the
session), a card's read or the act again pass; a search is refused with the datum it lacks. The hold clears when the
act runs or the question is asked. No counter: the twentieth search is refused for the same reason as the first.
Variants: two cards that declare the field; three refusals that declare none (they hold nothing).
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.cli import worker_api
from nucleo.workers import missing_datum
from nucleo.workers.session import SessionRecord


@pytest.fixture
def rec(monkeypatch):
    r = SessionRecord(task_id="7", goal="x")
    monkeypatch.setattr(worker_api, "classify_act", lambda a, p: worker_api.ALLOW)
    monkeypatch.setattr(worker_api, "_register_ask", lambda rec, q, **k: "corr-1")

    async def _no_cross(rec, action, payload):
        return None
    from nucleo.workers import exit_gate
    monkeypatch.setattr(exit_gate, "cross", _no_cross)
    from nucleo import circuit, network_rows_gate, on_his_behalf
    monkeypatch.setattr(on_his_behalf, "worker_question", lambda *a, **k: "")
    monkeypatch.setattr(network_rows_gate, "refused", lambda *a, **k: "")
    monkeypatch.setattr(circuit, "refused", lambda *a, **k: "")
    return r


def _card(monkeypatch, answer):
    async def _exec(action, payload, rec):
        return answer(action, payload)
    monkeypatch.setattr(worker_api, "_exec_allow", _exec)


def _act(rec, action, payload):
    return asyncio.run(worker_api._one_act(rec, action, payload))


@pytest.mark.parametrize("call,refusal", [
    ({"widget_id": "contactos", "action": "create_group", "payload": {}},
     {"ok": False, "error": "create_group needs the group's name", "field": "name"}),       # the card declares it
    ({"widget_id": "contactos", "action": "rename_group", "payload": {"name": "cena"}},
     {"ok": False, "error": "selector_missing", "field": "groupId"}),                      # the refusal names it
])
def test_a_refusal_for_a_missing_datum_holds_the_row_at_one_question(rec, monkeypatch, call, refusal):
    _card(monkeypatch, lambda a, p: refusal if a == "widget_data" else {"ok": True, "result": "found"})
    got = _act(rec, "widget_data", call)
    assert got["ok"] is False and got["missing"], got
    for _ in range(20):                      # no counter: every search is refused for the same reason
        out = _act(rec, "use_tool", {"tool": "web_search", "query": "q"})
        assert out.get("denied") and got["missing"][0] in out["error"]
    assert _act(rec, "read_widget", {"id": "contactos"})["ok"], "a card's read passes"
    asked = _act(rec, "ask_user", {"question": "¿Cómo se llama el grupo?"})
    assert asked["status"] == "pending", "the one question passes and parks the session"
    assert not rec.missing_datum
    assert _act(rec, "use_tool", {"tool": "web_search", "query": "q"})["ok"], "after his answer the row is free"


@pytest.mark.parametrize("refusal", [{"ok": False, "error": "not found"}, {"ok": False, "error": "channel down"},
                                     {"ok": False, "error": "widget_data falló: KeyError"}])
def test_a_refusal_that_declares_no_field_holds_nothing(rec, monkeypatch, refusal):
    """Audit #6: never a guess — `agenda:update_task {task,status}` refused for any cause, with `list,newTitle,date…`
    declared and empty, used to hold the row as if those were his data."""
    _card(monkeypatch, lambda a, p: refusal if a == "widget_data" else {"ok": True})
    _act(rec, "widget_data", {"widget_id": "agenda", "action": "update_task",
                              "payload": {"task": "x", "status": "done"}})
    assert not rec.missing_datum
    assert _act(rec, "use_tool", {"tool": "web_search"})["ok"]


def test_a_question_to_a_network_agent_does_not_answer_the_hold(rec, monkeypatch):
    from nucleo import mesh_jobs
    monkeypatch.setattr(mesh_jobs, "ask_for_worker", lambda rec, thread: "")
    _card(monkeypatch, lambda a, p: {"ok": False, "error": "x", "field": "name"} if a == "widget_data" else {"ok": True})
    _act(rec, "widget_data", {"widget_id": "contactos", "action": "create_group", "payload": {}})
    _act(rec, "ask_user", {"question": "q", "remote": {"thread": "t"}})
    assert rec.missing_datum, "only his question answers it"


def test_the_hold_rides_on_the_row_across_a_restart(rec, monkeypatch, tmp_path):
    from memory import db as memdb
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    try:
        rec.uid = "row-7"
        _card(monkeypatch, lambda a, p: {"ok": False, "error": "x", "field": "name"} if a == "widget_data"
              else {"ok": True})
        _act(rec, "widget_data", {"widget_id": "contactos", "action": "create_group", "payload": {}})
        again = SessionRecord(task_id="8", goal="x")
        again.uid = "row-7"                         # a new worker of the same row
        assert _act(again, "use_tool", {"tool": "web_search"}).get("denied")
    finally:
        memdb.reset_db()


def test_the_act_that_runs_clears_the_hold(rec, monkeypatch):
    _card(monkeypatch, lambda a, p: ({"ok": True} if (p.get("payload") or {}).get("name")
                                     else {"ok": False, "error": "needs name", "field": "name"}))
    _act(rec, "widget_data", {"widget_id": "contactos", "action": "create_group", "payload": {}})
    assert rec.missing_datum
    assert _act(rec, "widget_data", {"widget_id": "contactos", "action": "create_group",
                                     "payload": {"name": "cena"}})["ok"]
    assert not rec.missing_datum


def test_disarmed_without_the_hold_the_search_goes_on(rec, monkeypatch):
    """RED proof: with the hold disarmed the worker's chained searches run after the refusal (the measured class)."""
    monkeypatch.setattr(missing_datum, "held", lambda rec, action: "")
    _card(monkeypatch, lambda a, p: {"ok": False, "error": "x", "field": "name"} if a == "widget_data"
          else {"ok": True})
    _act(rec, "widget_data", {"widget_id": "contactos", "action": "create_group", "payload": {}})
    assert _act(rec, "use_tool", {"tool": "web_search"})["ok"]


def test_the_contacts_card_declares_the_missing_name():
    """The card says which datum it lacks: the hold has a declaration to read, not a guess."""
    import asyncio as _a

    from widgets.server_api import brain_action
    res = _a.run(brain_action("contactos", "create_group", {}))
    assert res.get("ok") is False and res.get("field") == "name"
