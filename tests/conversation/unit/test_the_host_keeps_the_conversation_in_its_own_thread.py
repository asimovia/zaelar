"""The host keeps the conversation in `zaelar.db`, written by its own thread only (node 13.36, v3.1 B1).

The rows of the `Store` port live in `conv_rows` / `conv_meta` of `zaelar.db` (schema v12; v13 adds the queue's columns), written through ONE
door (`memory.api.conv`) by ONE thread: the conversation's own, with its event loop, where entries are handed over
and its timer and the hourly prune run. A transaction there is exclusive on the shared connection: inside it no other
store can be reached (`Database.cursor()` refuses — it would commit the transaction half done). The prune drops what
is final and older than the horizon, never a row in course. The package's store contract (13.19), P3 one case in ten
and P8 run over this store too.
"""
from __future__ import annotations

import time

import pytest

from conversation import build
from conversation.ports import Done
from conversation.testing.fakes import AckingMouth, FakeOwed, ListTelemetry, NoMemory, RecordingTools
from conversation.testing.scripted_model import ScriptedModel, reply
from conversation.ear import signals as S
from memory.db import Database, exclusive
from memory.api import conv as cs
from nucleo.conversation_host.clock import SystemClock
from nucleo.conversation_host.runtime import ConversationRuntime
from nucleo.conversation_host.store import ZaelarStore


def test_the_schema_is_twelve_with_the_conversation_rows(tmp_path):
    db = Database(tmp_path / "z.db")
    assert db.schema_version() == 13 and {"conv_rows", "conv_meta"} <= db.tables()
    db.close()


def test_a_database_of_the_previous_version_gains_the_conversation_rows_and_keeps_its_own(tmp_path):
    db = Database(tmp_path / "z.db")
    with db.cursor() as cur:                              # what a v11 file looks like: no conversation, a memory of its own
        cur.execute("DROP TABLE conv_rows")
        cur.execute("DROP TABLE conv_meta")
        cur.execute("PRAGMA user_version=11")
        cur.execute("INSERT INTO sys_kv(key, value) VALUES ('k0', 'v0')")
    db.close()
    db = Database(tmp_path / "z.db")
    assert db.schema_version() == 13 and {"conv_rows", "conv_meta"} <= db.tables()
    with db.cursor() as cur:
        assert cur.execute("SELECT value FROM sys_kv WHERE key='k0'").fetchone()[0] == "v0"
    db.close()


def test_no_other_store_from_inside_a_transaction(tmp_path):
    db = Database(tmp_path / "z.db")
    with pytest.raises(RuntimeError, match="half done"):
        with exclusive(db):
            with db.cursor() as cur:                      # another store's write, from inside: refused, loudly
                cur.execute("SELECT 1")
    with db.cursor() as cur:                              # and the connection is usable after
        cur.execute("SELECT 1")
    db.close()


def test_the_prune_drops_what_is_final_and_old_never_what_is_in_course(tmp_path):
    db = Database(tmp_path / "z.db")
    old, new = ZaelarStore(db, clock_ms=lambda: 0), ZaelarStore(db, clock_ms=lambda: 40 * 86_400_000)
    lease = old.acquire("a", "p")
    with old.tx(lease) as tx:
        tx.put("inbox", "e1", {"state": "accounted"})     # final and old: goes
        tx.put("items", "r1", {"state": "open"})          # in course: stays, however old
        tx.put("items", "x1", {"state": "submission_unknown"})
    with new.tx(lease) as tx:
        tx.put("inbox", "e2", {"state": "accounted"})     # final and recent: stays
    assert cs.prune(30, 40 * 86_400_000, db=db) == 1
    snap = new.snapshot("a")
    assert snap.get("inbox", "e1") is None and snap.get("inbox", "e2") and snap.get("items", "r1")
    assert snap.get("items", "x1")
    db.close()


def test_the_conversation_lives_in_its_own_thread_and_writes_only_from_there(tmp_path):
    db = Database(tmp_path / "z.db")
    writers: set = set()

    class Watched(ZaelarStore):
        def tx(self, lease):
            import threading
            writers.add(threading.get_ident())
            return super().tx(lease)

    mouth = AckingMouth()

    def make():
        c = build(account="a", owner="host", model=ScriptedModel(default=lambda ids: [reply("w9"), Done()]),
                  tools=RecordingTools(), store=Watched(db), memory=NoMemory(), clock=SystemClock(), mouth=mouth,
                  telemetry=ListTelemetry(), owed=FakeOwed())
        mouth.ack = c.ack
        c.device("d1", voice_live=True, speaker_open=True)
        return c

    rt = ConversationRuntime(make, keep_time_ms=50, db=db).start()
    try:
        now = SystemClock().now_ms()
        rt.submit(lambda c: c.hear(S.TypedSubmit("d1", "c1", "w1", now))).result(5)
        deadline = time.monotonic() + 5
        while not mouth.orders and time.monotonic() < deadline:
            time.sleep(0.05)                               # the collect window, then the timer's pump
        assert [o.text for o in mouth.orders] == ["w9"]
        assert rt.submit(lambda c: rt.prune_now()).result(5) == 0
        assert writers == {rt.thread_id}                   # every transaction left from the conversation's thread
    finally:
        rt.stop()
        db.close()
