"""One task at a time per lane, in order, and the queue takes its tasks back after a restart (INI-078 Q-5, step 3).

His commission is born `pending` in the queue (`ledger.opened` → `queue.add`) and its session waits for its TURN at
the one place a session waits to run (`dispatch/session._a_slot` → `lanes.my_turn`). The pulse's beat (`lanes.tick`)
starts, in a lane with nothing running, the first pending task whose owner waits — unless the lane's gate holds it (the
worker lane's: the resource envelope). A task that waits for him or ends lets the next one start at once. Internal work
(memory, dev) is not a task: it waits only for measured room, as before.
"""
from __future__ import annotations

import asyncio
import types

from memory import tasks_store as ts
from nucleo import queue
from nucleo.queue import lanes


def _lane(results: dict, ids: list[str], *, gate=""):
    """Each id's owner waits for its turn on one loop; `results[id]` is set once its turn came."""
    lanes.gate("worker", lambda: gate)

    async def wait(tid):
        await lanes.my_turn(tid)
        results[tid] = ts.task_get(tid)["state"]
    return [asyncio.ensure_future(wait(t)) for t in ids]


def test_the_second_waits_pending_until_the_first_leaves_its_lane():
    results: dict = {}

    async def go():
        a, b = queue.add("worker", "flights to Rome"), queue.add("worker", "a table for four")
        waits = _lane(results, [a, b])
        await asyncio.sleep(0.05)
        assert results == {a: "running"} and ts.task_get(b)["state"] == "pending"
        queue.signal(a, "done", by="owner")             # it leaves: the next one starts now, not at the next beat
        await asyncio.sleep(0.05)
        assert results.get(b) == "running"
        await asyncio.gather(*waits)
    asyncio.run(go())


def test_one_that_waits_for_him_steps_aside_and_the_next_starts():
    results: dict = {}

    async def go():
        a, b = queue.add("worker", "book the table"), queue.add("worker", "compare monitors")
        waits = _lane(results, [a, b])
        await asyncio.sleep(0.05)
        queue.signal(a, "wait", by="owner", ask="9 or 9:30?")
        await asyncio.sleep(0.05)
        assert results.get(b) == "running" and ts.task_get(a)["state"] == "waiting"
        await asyncio.gather(*waits)
    asyncio.run(go())


def test_an_urgent_one_is_the_next_to_start():
    results: dict = {}

    async def go():
        busy = queue.add("worker", "running now")
        waits = _lane(results, [busy])
        await asyncio.sleep(0.05)
        a = queue.add("worker", "first")
        b = queue.add("worker", "second")
        u = queue.add("worker", "it's urgent", urgent=True)
        waits += _lane(results, [a, b, u])
        await asyncio.sleep(0.05)
        queue.signal(busy, "done", by="owner")
        await asyncio.sleep(0.05)
        assert list(results) == [busy, u], "the urgent one is the next to start"
        queue.signal(u, "done", by="owner")
        await asyncio.sleep(0.05)
        assert list(results) == [busy, u, a]
        queue.signal(a, "done", by="owner")
        await asyncio.sleep(0.05)
        await asyncio.gather(*waits)
    asyncio.run(go())


def test_the_lanes_gate_holds_its_next_task_and_says_why():
    told = []

    async def go():
        a = queue.add("worker", "a heavy search")
        lanes.gate("worker", lambda: "waiting_voice")
        w = asyncio.ensure_future(lanes.my_turn(a, held=told.append))
        await asyncio.sleep(0.05)
        assert ts.task_get(a)["state"] == "pending" and told == ["waiting_voice"]
        lanes.gate("worker", lambda: "")
        assert lanes.tick() == [a]
        await asyncio.wait_for(w, 1)
    asyncio.run(go())


def test_his_commission_is_born_in_the_queue_and_internal_work_is_not():
    from nucleo.circuit import ledger
    mine = types.SimpleNamespace(task_id="41", goal="find a flat in Leeds", kind="web", title="", surface="", sheet="")
    uid = ledger.opened(mine, {"origin": "voz", "trace": "tr-1"})
    row = ts.task_get(uid)
    assert row["owner"] == "worker" and row["state"] == "pending" and row["num"] and row["trace_id"] == "tr-1"
    internal = types.SimpleNamespace(task_id="42", goal="tidy the memory", kind="memory", title="", surface="",
                                     sheet="")
    assert not ts.task_get(ledger.opened(internal, {"origin": "voz"})).get("owner")


def test_a_session_of_his_waits_for_its_turn_where_every_session_waits():
    from nucleo import dispatch
    from nucleo.dispatch import session
    entered = []

    async def go():
        lanes.gate("worker", lambda: "")
        a = queue.add("worker", "running already")
        queue.signal(a, "start", by="pulse")
        b = queue.add("worker", "next in line")
        rec = types.SimpleNamespace(uid=b, held="", status="queued", surface="", session=None)

        async def run():
            async with session._a_slot(dispatch, "7", rec):
                entered.append(ts.task_get(b)["state"])
        t = asyncio.ensure_future(run())
        await asyncio.sleep(0.05)
        assert entered == [] and rec.held, "it waits, and the record says it has not started"
        queue.signal(a, "done", by="owner")
        await asyncio.wait_for(t, 1)
        assert entered == ["running"] and rec.held == ""
    asyncio.run(go())


def test_after_a_restart_the_queue_takes_its_tasks_back():
    from nucleo.queue import boot
    ran = queue.add("worker", "was running")
    queue.signal(ran, "start", by="pulse")
    waits = queue.add("worker", "was waiting for him")
    queue.signal(waits, "start", by="pulse")
    queue.signal(waits, "wait", by="owner", ask="which one?")
    old = "abc-9"                       # a live commission written before the queue existed
    ts.task_put({"id": old, "title": "an old search", "goal": "an old search", "kind": "web", "state": "running",
                 "visible": True, "created_at": 1})
    plan = boot.at_boot(schedule=False)
    assert plan["adopted"] == [old] and ts.task_get(old)["owner"] == "worker" and ts.task_get(old)["num"]
    assert plan["back"] == [ran] and ts.task_get(ran)["state"] == "pending"
    assert set(plan["relaunched"]) == {ran, old} and ts.task_get(waits)["state"] == "waiting"
    assert [r["id"] for r in queue.view()["worker"]["pending"]][0] == ran, "the one that ran goes first"
    assert boot.at_boot(schedule=False)["adopted"] == [], "once: a task of the queue is not adopted again"


def test_a_task_that_leaves_while_its_owner_waits_never_leaves_it_waiting():
    """Cancelled (or archived) while its session waits for its turn: the waiter wakes at once and never runs."""
    async def go():
        lanes.gate("worker", lambda: "")
        busy = queue.add("worker", "running now")
        queue.signal(busy, "start", by="pulse")
        b = queue.add("worker", "next in line")
        w = asyncio.ensure_future(lanes.my_turn(b))
        await asyncio.sleep(0.05)
        assert not w.done()
        queue.signal(b, "cancelled", by="him")
        try:
            await asyncio.wait_for(w, 1)
        except lanes.Left:
            return "left"
        return "ran"
    assert asyncio.run(go()) == "left"


def test_a_task_of_the_queue_is_not_resumed_twice_at_boot(monkeypatch):
    """`rehydrate` leaves a task of the queue alone: the queue relaunches it, once."""
    from nucleo.pulse import rehydrate
    tid = queue.add("worker", "a search cut by the restart")
    queue.signal(tid, "start", by="pulse")
    monkeypatch.setattr(rehydrate, "snapshot", lambda: {"at": 1.0, "sessions": [
        {"id": "5", "uid": tid, "goal": "a search cut by the restart", "kind": "web", "status": "running"}]})
    monkeypatch.setattr(rehydrate, "forget", lambda: None)
    monkeypatch.setattr("nucleo.runstate.blocks_new_work", lambda who="": False)
    from nucleo.queue import boot
    assert boot.at_boot(schedule=False)["relaunched"] == [tid]
    plan = rehydrate.at_boot(schedule=False)
    assert tid not in [e.get("uid") for e in plan.get("resume", []) + plan.get("buried", [])]


def test_a_task_cancelled_before_its_session_waits_ends_that_session_at_once():
    """Cancelled between its birth and its session reaching its turn: the row is gone, and the waiter leaves at once."""
    async def go():
        tid = queue.add("worker", "cancelled too soon")
        queue.signal(tid, "cancelled", by="him")
        try:
            await asyncio.wait_for(lanes.my_turn(tid), 1)
        except lanes.Left:
            return "left"
        return "ran"
    assert asyncio.run(go()) == "left"


def test_a_died_worker_resumed_by_id_runs_when_its_turn_comes():
    """A worker that died waits for its relaunch; relaunched, its session finds it WAITING and puts it back first."""
    from nucleo.circuit import waits

    async def go():
        lanes.gate("worker", lambda: "")
        busy = queue.add("worker", "running now")
        queue.signal(busy, "start", by="pulse")
        died = queue.add("worker", "a worker that died")
        queue.signal(busy, "wait", by="owner", ask="?")        # the lane frees: `died` would start…
        queue.signal(died, "start", by="pulse")
        assert waits.waiting(died, waits.WORKER)               # …and its process dies: it waits for its relaunch
        assert ts.task_get(died)["state"] == "waiting"
        w = asyncio.ensure_future(lanes.my_turn(died))        # the relaunched session asks for its turn
        await asyncio.wait_for(w, 1)
        return ts.task_get(died)["state"]
    assert asyncio.run(go()) == "running"


def test_his_answer_puts_his_task_first_in_line_never_beside_the_running_one():
    from nucleo.circuit import waits
    asked = queue.add("worker", "asked him something")
    queue.signal(asked, "start", by="pulse")
    assert waits.waiting(asked, waits.USER_ANSWER, ask="which date?")
    other = queue.add("worker", "runs meanwhile")
    queue.signal(other, "start", by="pulse")
    waits.resumed(asked)                                        # his answer
    assert ts.task_get(asked)["state"] == "pending" and ts.task_get(other)["state"] == "running"
    assert queue.view()["worker"]["pending"][0]["id"] == asked


def test_a_second_session_for_a_waiting_task_leaves_and_the_first_still_runs():
    async def go():
        lanes.gate("worker", lambda: "")
        busy = queue.add("worker", "running now")
        queue.signal(busy, "start", by="pulse")
        b = queue.add("worker", "next in line")
        first = asyncio.ensure_future(lanes.my_turn(b))
        await asyncio.sleep(0.02)
        second = asyncio.ensure_future(lanes.my_turn(b))
        await asyncio.sleep(0.02)
        assert isinstance(second.exception(), lanes.Left), "a second session never runs beside the first"
        queue.signal(busy, "done", by="owner")
        await asyncio.wait_for(first, 1)
        return ts.task_get(b)["state"]
    assert asyncio.run(go()) == "running"
