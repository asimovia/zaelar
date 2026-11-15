"""A card that refuses a worker's act for a datum only he can give holds the row at ONE question (mechanism).

Measured: a worker whose card refused its act for a missing name went on to ~20 chained searches for more than 15
minutes. Now the refusal names the datum and the bridge holds the row: only the question to him (which parks the
session), a card's read or the act again pass; a search is refused with the datum it lacks. The hold clears when the
act runs or the question is asked. No counter: the twentieth search is refused for the same reason as the first.
Variants: a datum the refusal names (`field`) and a declared required field the call left empty, on two cards.
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
     {"ok": False, "error": "create_group needs the group's name"}),                       # declared, left empty
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
    assert rec.missing_datum is None
    assert _act(rec, "use_tool", {"tool": "web_search", "query": "q"})["ok"], "after his answer the row is free"


def test_a_refusal_with_every_datum_given_holds_nothing(rec, monkeypatch):
    _card(monkeypatch, lambda a, p: {"ok": False, "error": "duplicate"} if a == "widget_data" else {"ok": True})
    _act(rec, "widget_data", {"widget_id": "contactos", "action": "create_group", "payload": {"name": "cena"}})
    assert rec.missing_datum is None
    assert _act(rec, "use_tool", {"tool": "web_search"})["ok"]


def test_the_act_that_runs_clears_the_hold(rec, monkeypatch):
    calls = []
    _card(monkeypatch, lambda a, p: ({"ok": True} if (p.get("payload") or {}).get("name") or calls.append(1)
                                     else {"ok": False, "error": "needs name"}))
    _act(rec, "widget_data", {"widget_id": "contactos", "action": "create_group", "payload": {}})
    assert rec.missing_datum
    assert _act(rec, "widget_data", {"widget_id": "contactos", "action": "create_group",
                                     "payload": {"name": "cena"}})["ok"]
    assert rec.missing_datum is None


def test_disarmed_without_the_hold_the_search_goes_on(rec, monkeypatch):
    """RED proof: with the hold disarmed the worker's chained searches run after the refusal (the measured class)."""
    monkeypatch.setattr(missing_datum, "held", lambda rec, action: "")
    _card(monkeypatch, lambda a, p: {"ok": False, "error": "x"} if a == "widget_data" else {"ok": True})
    _act(rec, "widget_data", {"widget_id": "contactos", "action": "create_group", "payload": {}})
    assert _act(rec, "use_tool", {"tool": "web_search"})["ok"]


def test_a_field_marked_optional_is_never_a_missing_datum():
    assert missing_datum.required_empty("contactos", "create_group", {"name": "cena"}) == []
    assert missing_datum.required_empty("contactos", "create_group", {}) == ["name"]
