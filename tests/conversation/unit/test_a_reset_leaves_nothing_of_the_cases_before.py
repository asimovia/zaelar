"""A sandbox's reset leaves nothing of the cases before it (node 13.83, V2-941).

Between two isolated test conversations a disposable engine resets: the conversation's rows go and its lease is fenced
at its epoch, so the next manager mints its ids in a space of its own — `iv_000001` never names two conversations of
one engine, and a manager still running from before is refused at its next write. What the cases WROTE to memory goes
too: the first reset marks where the cases begin (after the seed), every later one forgets what was written since, and
the conversation buffer whatever its age. A flow read by an id is its NEWEST rows, in order, from `since` on. A real
engine refuses the reset (`test_the_smokes_findings_hold`).
"""
from __future__ import annotations

import asyncio

import pytest

from conversation.types import Ids
from memory.conversation_store import StaleEpoch, acquire, current, tx, wipe


def test_the_lease_is_fenced_and_the_next_manager_mints_ids_of_its_own(tmp_path):
    from memory.db import Database
    db = Database(tmp_path / "z.db")
    try:
        assert acquire("a", "m1", db=db) == 1
        with tx("a", "m1", 1, 0, db=db) as t:
            t.put("inbox", "e1", {"id": "e1"})
        assert wipe("a", db=db) == 1
        assert current("a", db=db) == ("", 1)                             # fenced, never forgotten
        with pytest.raises(StaleEpoch):                                    # the manager from before: refused
            with tx("a", "m1", 1, 0, db=db) as t:
                t.put("inbox", "e2", {"id": "e2"})
        epoch = acquire("a", "m2", db=db)
        assert epoch == 2
        space = "" if epoch == 1 else f"{epoch}x"                          # `Conversation.__init__`'s rule
        assert Ids(space).new("iv") != Ids("").new("iv")
    finally:
        db.close()


def test_what_the_cases_wrote_is_forgotten_and_the_seed_stays():
    from memory import api as memory
    from memory import db as _db
    from nucleo.conversation_host import sandbox
    sandbox._mark["memory"] = None
    seed = memory.write_now("w0101 seed", kind="contact")
    sandbox.forget_cases()                                                 # the first reset: the mark, after the seed
    fact = memory.write_now("w0201 a fact a case left", kind="fact")
    pair = memory.write_now("Operador: w0301 · zaelar: w0302", kind="conv", level="short", meta={"source": "conv"})
    assert sandbox.forget_cases() == 2
    valid = {r["id"] for r in _db.get_db().query("SELECT id FROM memories WHERE valid=1")}
    assert seed in valid and fact not in valid and pair not in valid
    sandbox._mark["memory"] = None


def test_the_reset_door_drains_the_memory_queue_then_resets(monkeypatch):
    from nucleo.conversation_host import sandbox
    from server import voice_api
    monkeypatch.setenv("ZAELAR_CONVERSATION_SANDBOX", "1")
    order = []

    class _Q:
        async def join(self):
            order.append("drained")

    monkeypatch.setattr("memory.queue.get_queue", lambda: _Q())
    monkeypatch.setattr(sandbox, "reset", lambda: order.append("reset") or {"rows": 3, "memories": 2})
    got = asyncio.run(voice_api.debug_conversation_reset())
    assert got.status_code == 200 and order == ["drained", "reset"]


@pytest.fixture()
def events(tmp_path, monkeypatch):
    from bus import log as buslog
    monkeypatch.setattr(buslog, "_conn", None)
    monkeypatch.setattr(buslog, "db_path", lambda: tmp_path / "zaelar.db")
    yield lambda rows: buslog._insert([buslog._row({"ts_ms": ts, "topic": "observer", "payload": p}) for ts, p in rows])
    if buslog._conn is not None:
        buslog._conn.close()


def test_a_flow_is_its_newest_rows_in_order_from_since_on(events):
    from observability import flows
    old = [(1000 + i, {"kind": "conv_run", "label": f"old{i}", "trace": "iv_000001"}) for i in range(3)]
    new = [(9000 + i, {"kind": "conv_run", "label": f"new{i}", "trace": "iv_000001"}) for i in range(3)]
    events(old + new)
    assert [r["label"] for r in flows.flow("iv_000001", limit=3)] == ["new0", "new1", "new2"]
    assert [r["label"] for r in flows.flow("iv_000001", since_ms=9001)] == ["new1", "new2"]
    assert len(flows.flow("iv_000001")) == 6
