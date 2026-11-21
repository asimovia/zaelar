"""The engine's counters fold and count discards apart (node 13.142, E7d-6, R-1).

A session counts, with ONE definition (`observability/flows.counts`): its TURNS (flows he started), its EVENTS (flows
the system started), its FLOWS (those with a real step — an old flow that says no steps counts), its TASKS (the workers
spawned, or the tasks a turn's end says it opened) and its DISCARDS apart; a flow folded into another counts nowhere,
and never one per `corr_id`. The list of a session's flows holds only those that stand, unless every row is asked.
"""
from __future__ import annotations

import pytest

from bus import log as buslog
from observability import flows

SID = "s_w1"
T0 = 1_800_000_000_000.0


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(buslog, "_conn", None)
    monkeypatch.setattr(buslog, "db_path", lambda: tmp_path / "zaelar.db")
    yield lambda rows: buslog._insert([buslog._row({"ts_ms": T0 + i, "topic": topic, "payload": {"sid": SID, **p}})
                                       for i, (topic, p) in enumerate(rows)])
    if buslog._conn is not None:
        buslog._conn.close()


def _root(trace, origin, initiator, text="w_x"):
    return ("observer", {"trace": trace, "kind": "trace", "label": origin, "text": text, "initiator": initiator})


def _end(trace, **extra):
    return ("observer", {"trace": trace, "kind": "flow", "label": "end", "cat": "conversation", **extra})


def test_a_session_counts_turns_flows_tasks_events_and_discards_with_one_definition(db):
    db([_root("T1", "turno", "user"), _end("T1", steps=2, tasks=1),
        ("worker.spawned", {"trace": "T1", "id": "w_task1"}),
        _root("T2", "turno", "user"), _end("T2", steps=0, tasks=0),                 # a turn with no real step
        _root("T3", "turno", "user"), ("observer", {"trace": "T3", "kind": "trace", "label": "merge",
                                                    "merge_into": "T1"}),            # folded into T1
        ("observer", {"trace": "iv9", "kind": "flow", "label": "end", "discarded": "echo"}),   # the ear's discard
        _root("E1", "connector.msg", "system"), _end("E1", steps=1, tasks=0),
        _root("E2", "cron.due", "system"), _end("E2", steps=0, tasks=0, discarded="nothing"),
        _root("O1", "turno", "user")])                                               # an old flow: no steps said
    got = flows.session(SID)
    assert {k: got[k] for k in ("turns", "flows", "tasks", "event_flows", "discards")} == {
        "turns": 3, "flows": 3, "tasks": 1, "event_flows": 1, "discards": 2}
    assert got["events"] > 10, "the session's own count of rows is never overwritten by a flow counter"
    row = next(r for r in flows.sessions(limit=5) if r["session_id"] == SID)
    assert row["flows"] == 3 and row["discards"] == 2
    rows = flows.flows(limit=50, session_id=SID)
    assert sorted(r["corr_id"] for r in flows.standing(rows)) == ["E1", "O1", "T1", "T2"]
