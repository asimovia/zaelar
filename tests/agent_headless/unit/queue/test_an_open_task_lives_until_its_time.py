"""An open task lives until its own time, and then it is archived and said once (INI-078 #5, commit a).

One kind of task; what changes is how long it lives: `lives_until`, from his order when it bounds it («within three
hours», «en dos días») or set by its owner from what it learns. Past it, an open task that is not running — pending or
waiting — is archived (`cancelled`, «expired») by the pulse's sweep and said in ONE line keyed to it; a running one is
alive by its own beat. The pulse wakes for the next such instant. Nothing dies in silence, and nothing is deleted.
"""
from __future__ import annotations

import asyncio
import time

from memory import tasks_store as ts
from nucleo import queue


def test_his_order_sets_how_long_it_lives_and_plain_words_do_not():
    now = 1_000_000.0
    assert queue.lives_for("find me a table within 3 hours", now) == now + 3 * 3600
    assert queue.lives_for("búscame piso para los próximos 2 días", now) == now + 2 * 86400
    assert queue.lives_for("find me a flat in Leeds", now) is None


def test_a_commission_is_born_with_the_life_its_order_gives():
    from nucleo.circuit import ledger

    class Rec:
        uid, task_id, title, kind, surface, sheet = "w-1", "1", "w_table", "web", "", ""
        goal = "find me a table for four within 2 hours"
    before = time.time()
    uid = ledger.opened(Rec(), {"origin": "voz"})
    lives = ts.task_get(uid)["lives_until"]
    assert before + 2 * 3600 - 5 <= lives <= time.time() + 2 * 3600 + 5


def test_an_open_task_past_its_time_is_archived_and_a_running_one_lives_on():
    now = int(time.time())
    pending = queue.add("worker", "w_pending", lives_until=int(now - 1))
    waiting = queue.add("send", "w_waiting", lives_until=int(now - 1))
    queue.signal(waiting, "start", by="owner")
    queue.signal(waiting, "wait", by="owner", ask="w_which?")
    running = queue.add("processor", "w_running", lives_until=int(now - 1))
    queue.signal(running, "start", by="pulse")
    later = queue.add("worker", "w_later", lives_until=int(now + 600))
    gone = queue.expired(now)
    assert sorted(r["id"] for r in gone) == sorted([pending, waiting])
    for tid in (pending, waiting):
        row = ts.task_get(tid)
        assert (row["state"], row["outcome"]) == ("cancelled", "expired: its time ran out")
    assert ts.task_get(running)["state"] == "running" and ts.task_get(later)["state"] == "pending"
    assert queue.expired(now) == [], "archived once"
    assert queue.next_expiry(now) == float(now + 600) and queue.next_expiry(now + 601) is None


def test_the_pulse_wakes_for_it_archives_it_and_says_one_line(monkeypatch):
    from nucleo import dispatch
    from nucleo.pulse import deadlines, notices
    from nucleo.pulse.loop import OrchestratorLoop
    from voice.engine.core import langs
    said = []

    async def _notify(title, text, *, key, kind="reminder", **k):
        said.append((text, key, kind))
        return {"id": 1, "state": "spoken", "channel": "voice", "duplicate": False}
    monkeypatch.setattr(notices, "notify", _notify)
    monkeypatch.setattr(dispatch, "sync_state", lambda: None)
    monkeypatch.setattr(dispatch, "active_sessions", lambda: [])
    monkeypatch.setattr(dispatch, "unclosed_uids", lambda: set())
    now = int(time.time())
    tid = queue.add("worker", "w_tickets", lives_until=int(now + 30))
    assert deadlines.upcoming(now)["task"] == float(now + 30), "a sleeping engine is woken for it"

    async def _noop(*a, **k):
        return None
    asyncio.run(OrchestratorLoop(deliver=_noop)._supervise_workers(now + 31))
    assert ts.task_get(tid)["state"] == "cancelled"
    line = langs.current_language().task_life_over.format(goal="w_tickets")
    assert said == [(line, f"task:{tid}:expired", "info")]
