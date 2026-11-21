"""A live task list a restart finds is archived (INI-078, Q-7): lists no longer exist, so nothing would ever run it.

One short pill per list says what it was, and the list and its steps leave the task table; an ended list is history and
is left to its own prune.
"""
from __future__ import annotations


def test_a_live_list_a_restart_finds_is_archived_with_its_steps(monkeypatch):
    from memory import api as memory, tasks_store as ts
    from nucleo.circuit import ledger
    pills = []
    monkeypatch.setattr(memory, "write", lambda text, **kw: pills.append((text, kw)))
    ts.task_put({"id": "lista:1", "title": "2 × call the garage", "kind": "lista", "state": "running"})
    ts.task_put({"id": "lista:1#01", "title": "call the garage", "kind": "other", "parent_id": "lista:1"})
    ts.task_put({"id": "lista:0", "title": "an old list", "kind": "lista", "state": "done"})
    ts.artifact_put("lista:1#01", "report", {"said": "garage called"})
    assert ledger.lists_retired() == 1
    assert ts.task_get("lista:1") is None and ts.task_get("lista:1#01") is None
    assert ts.artifacts_of("lista:1#01") == {}, "no artifact is left behind without its row"
    assert ts.task_get("lista:0") is not None, "an ended list is history, left to its own prune"
    (text, kw), = pills
    assert text.startswith("2 × call the garage") and kw["kind"] == "task" and kw["meta"]["task_id"] == "lista:1"
    assert ledger.lists_retired() == 0, "idempotent: an archived list is gone"
