"""A step of his list is HIS request to the conversation manager (INI-078 F2, after the unplug).

The list used to run each step as a turn of the old path. The manager is the only path now: each step enters through
the same door as a line he types (`runner.by_the_manager` → `entry.typed_and_wait`, his authority, never an event's),
and the list reads its answer as it read a turn's — what it said, the acts that LANDED (`acts`, the typed door's report
of the run's submitted acts and their receipts). When the manager may not run, the step fails with the reason: there is
no other path, and nothing of the old turn is reached.
"""
import asyncio

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from nucleo.batch import runner

STEPS = [{"id": "1", "title": "dentist", "say": "w_put the dentist on friday at nine", "kind": "agenda"}]


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    mememb.reset(); memdb.reset_db(); memdb.get_db()
    monkeypatch.setattr(runner, "_SETTLE_S", 0.0)
    monkeypatch.setattr(runner, "_worker_state", lambda tid: "done")
    yield
    memdb.reset_db(); mememb.reset()


def _run(monkeypatch, answer, *, on=True):
    from nucleo.conversation_host import entry, switch
    seen, told = [], []
    monkeypatch.setattr(switch, "on", lambda session=None: on)
    monkeypatch.setattr(switch, "decide", lambda *a, **k: switch.Decision(on, "manager", "" if on else "w_why"))

    async def typed_and_wait(text, dev="", **kw):
        seen.append((text, dev))
        return answer

    async def ingest(text):
        return None

    async def notify(title, text):
        told.append(text)
    monkeypatch.setattr(entry, "typed_and_wait", typed_and_wait)
    uid = runner.create("msg", STEPS, origin="chat")
    asyncio.run(runner.run(uid, notify=notify, worker_wait_s=0.1))
    return uid, seen, told


def test_each_step_enters_the_manager_by_his_door_and_an_act_that_landed_is_done(monkeypatch):
    uid, seen, _told = _run(monkeypatch, {"ok": True, "reply": "w_done, friday at nine",
                                          "acts": [{"name": "agenda_add", "status": "ok"}]})
    assert seen == [(STEPS[0]["say"], f"list:{uid}")], "his line, at the typed door, named for his list"
    assert [r["state"] for r in runner.steps_of(uid)] == ["done"]


def test_a_step_whose_act_never_landed_is_not_done(monkeypatch):
    uid, _seen, _told = _run(monkeypatch, {"ok": True, "reply": "w_done", "acts": [{"name": "agenda_add",
                                                                                    "status": "rejected"}]})
    assert [r["state"] for r in runner.steps_of(uid)] == ["failed"]


def test_with_the_manager_unable_to_run_the_step_fails_with_the_reason(monkeypatch):
    uid, seen, _told = _run(monkeypatch, {"ok": True, "reply": "w_never"}, on=False)
    rows = runner.steps_of(uid)
    assert seen == [] and [r["state"] for r in rows] == ["failed"] and "w_why" in str(rows[0].get("outcome") or "")


def test_the_typed_door_reports_the_acts_of_its_run_and_what_they_answered():
    """The typed door's report carries the acts its run submitted and their receipts' status — what the list judges a
    step by (an act that landed), read off the gateway's own events for that request."""
    import concurrent.futures
    import threading

    from nucleo.conversation_host import entry
    cid = "c_list1"
    entry._waits[cid] = {"iv": None, "future": concurrent.futures.Future(), "said": [], "reads": [], "acts": [],
                         "ended": threading.Event()}
    try:
        entry._listen("conv_ear", "typed", {"cause": {"ref": cid}, "refs": {"iv": "iv_9"}})
        entry._listen("conv_effect", "submitted", {"refs": {"req": "r_iv_9"}, "tool": "agenda_add"})
        entry._listen("conv_effect", "receipt", {"refs": {"req": "r_iv_9"}, "status": "ok"})
        entry._listen("conv_effect", "submitted", {"refs": {"req": "r_iv_other"}, "tool": "w_not_ours"})
        assert entry._waits[cid]["acts"] == [{"name": "agenda_add", "status": "ok"}]
    finally:
        entry._waits.pop(cid, None)


def test_his_words_are_filed_one_at_a_time_and_in_order(monkeypatch):
    """The list files nothing of its own: the manager files his words of each answered step through the memory's one
    writer, which takes them ONE AT A TIME and IN ORDER — the distiller is never asked for a list's steps at once."""
    from nucleo import memory_agent
    from nucleo.memory_agent import ingest as _ingest
    log, inside = [], {"n": 0, "max": 0}

    async def locked(text, *, role="operator"):
        inside["n"] += 1
        inside["max"] = max(inside["max"], inside["n"])
        log.append(text)
        await asyncio.sleep(0.01)
        inside["n"] -= 1
        return {"atoms": 1}
    monkeypatch.setattr(_ingest, "_ingest_utterance_locked", locked)
    monkeypatch.setattr(_ingest, "_HOME_LOOP", None)

    async def go():
        await asyncio.gather(*(memory_agent.ingest_utterance(f"w_step {i}") for i in range(5)))
    asyncio.run(go())
    assert log == [f"w_step {i}" for i in range(5)] and inside["max"] == 1


def test_a_list_steps_line_and_our_answer_never_reach_the_wall(monkeypatch):
    """Only the list's report is said: a step's line and the manager's answer to it run and are recorded in their
    flow, and the wall paints neither — a line he typed himself still lands there."""
    from types import SimpleNamespace

    from nucleo.conversation_host import wall
    from voice import observer
    painted = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, **kw: painted.append(kw.get("extra", {}).get("writer"))
                        if kind == "wall" else None)
    wall._accepted("user.text", "iv_list1", f"{wall.OFF_WALL}u1", "w_put the dentist on friday")
    wall.ours(SimpleNamespace(endpoint=f"{wall.OFF_WALL}u1", request_id="r_iv_list1", run_id="run1", say_id="s1",
                              text="w_done"), "shown")
    assert painted == []
    wall._accepted("user.text", "iv_his", "desktop:d1", "w_hello")
    assert painted == ["keyboard:desktop:d1"]
