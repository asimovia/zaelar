"""V2-931 · His stop ends the process at once — whatever state it is in.

Measured on his engine (2026-11-17, 23:10): with a task waiting on «shall I change your widget?», «stop every change
to any widget, I never asked for that» was handed to the task as words («OK, I'll pass it to the task») and the task
stayed open until he pressed its button seventeen minutes later. A stop is not a sentence for the worker to read: the
switchboard reads it (`"is": "stop"`, every process with `"all": true`) and ends the row through its ONE cancel door
(`dispatch.control.cancel_row`, the screen's button): a running worker's session is told to stop (signal, grace,
kill), a queued one never starts, a waiting question is closed, the row ends `cancelled`, and he hears one line.
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo import dispatch
from nucleo.switchboard import act, board, route


class _Session:
    """A worker session as the stop door drives it: `stop(reason=…)` is the signal → grace → kill of its backend."""

    def __init__(self):
        self.stops, self.alive = [], True

    async def stop(self, *, grace: float = 3.0, reason: str = "") -> None:
        self.stops.append(reason)
        self.alive = False


@pytest.fixture
def desk(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    got = SimpleNamespace(procs=[], said=[], events=[], relayed=[], answers=[])
    monkeypatch.setattr(board, "open_processes", lambda: [dict(p) for p in got.procs])
    monkeypatch.setattr(route, "_declared_answer", lambda text, procs: (None, ""))
    monkeypatch.setattr(dispatch, "relay_his_words", lambda which, words: got.relayed.append(words) or True)
    from nucleo.cli import worker_api
    monkeypatch.setattr(worker_api, "answer_soon", lambda *a, **k: got.answers.append(a) or True)
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda *a, **k: None)
    route._seen.update(text="", key="", at=0.0)
    route._piece.update(text="", at=0.0)
    got.emit = lambda kind, label, text="", role="", extra=None: got.events.append(dict(extra or {}))
    got.model = lambda n, kind: monkeypatch.setattr(
        route, "ask_the_model", lambda text, procs, last="", before=None: (n, "double", kind))
    yield got
    dispatch._SESSIONS.clear()
    memdb.reset_db()


def _row(uid: str, state: str, title: str) -> None:
    ts.task_put({"id": uid, "goal": title, "title": title, "state": state, "created_at": int(time.time())})


def _proc(uid: str, title: str, *, tid: str = "", state: str = "running", ask_id: str = "") -> dict:
    return {"key": uid, "dispatch": tid, "title": title, "state": state, "question": "Shall I?" if ask_id else "",
            "ask_id": ask_id, "since": 0}


def _say(desk, text: str) -> bool:
    async def go():
        took = await route.take(text, emit=desk.emit, say=desk.said.append)
        await asyncio.sleep(0.02)                     # the session's stop is scheduled on the loop
        return took
    return asyncio.run(go())


def _line(key: str) -> str:
    from i18n import langs
    return str(getattr(langs.current_language(), key))


def test_a_running_worker_is_stopped_and_its_row_ends(desk):
    _row("s1-1", "running", "Compare three laptops")
    sess = _Session()
    dispatch._SESSIONS["4"] = SimpleNamespace(uid="s1-1", status="running", task_id="4", session=sess, task=None,
                                              settled="", trace_id="", label="", goal="Compare three laptops")
    desk.procs = [_proc("s1-1", "Compare three laptops", tid="4")]
    desk.model(1, "stop")
    assert _say(desk, "para eso, déjalo") is True
    assert sess.stops == ["operator"] and not sess.alive, "its session was not told to stop"
    assert "4" not in dispatch._SESSIONS and ts.task_get("s1-1")["state"] == "cancelled"
    assert desk.said == [_line("stopped_now")] and desk.relayed == [], "a stop is never words for the worker to read"
    assert desk.events[-1]["is"] == "stop" and desk.events[-1]["delivered"] is True


def test_a_queued_worker_that_has_no_session_yet_never_starts(desk):
    _row("s1-2", "running", "Draft the trip plan")

    async def go():
        waiting = asyncio.ensure_future(asyncio.sleep(60))            # held: waiting for room, no process yet
        dispatch._SESSIONS["5"] = SimpleNamespace(uid="s1-2", status="queued", task_id="5", session=None, task=waiting,
                                                  settled="", trace_id="", label="", goal="Draft the trip plan")
        took = await route.take("cancela ese", emit=desk.emit, say=desk.said.append)
        await asyncio.sleep(0.02)
        return took, waiting.cancelled()
    desk.procs = [_proc("s1-2", "Draft the trip plan", tid="5")]
    desk.model(1, "stop")
    assert asyncio.run(go()) == (True, True)
    assert "5" not in dispatch._SESSIONS and ts.task_get("s1-2")["state"] == "cancelled"


def test_a_process_waiting_on_his_answer_is_closed_not_answered(desk):
    """23:10 — the task parked on «shall I change your widget?»: his stop closes it; nothing is «passed on»."""
    _row("s1-3", "waiting", "Change the messaging widget")
    desk.procs = [_proc("s1-3", "Change the messaging widget", state="waiting", ask_id="s1-3-start-b-1")]
    desk.model(1, "stop")
    assert _say(desk, "para todas las modificaciones de ningún widget, yo no te he pedido eso") is True
    assert ts.task_get("s1-3")["state"] == "cancelled" and desk.answers == [] and desk.relayed == []
    assert desk.said == [_line("stopped_now")]


def test_stop_everything_ends_every_open_process(desk):
    _row("s1-4", "running", "Search flights")
    _row("s1-5", "waiting", "Book the table")
    sess = _Session()
    dispatch._SESSIONS["6"] = SimpleNamespace(uid="s1-4", status="running", task_id="6", session=sess, task=None,
                                              settled="", trace_id="", label="", goal="Search flights")
    desk.procs = [_proc("s1-4", "Search flights", tid="6"),
                  _proc("s1-5", "Book the table", state="waiting", ask_id="s1-5-a")]
    desk.model(1, "stop_all")
    assert _say(desk, "para todo") is True
    assert [ts.task_get(u)["state"] for u in ("s1-4", "s1-5")] == ["cancelled", "cancelled"] and sess.stops == ["operator"]
    assert desk.said == [_line("stopped_now")], "one line for the whole stop"


def test_the_decision_reads_a_stop_and_a_stop_of_everything(monkeypatch):
    from nucleo.memory_agent.processor import llm
    procs = [_proc("a", "Search flights"), _proc("b", "Book the table")]
    monkeypatch.setattr(llm, "chat_sync", lambda *a, **k: '{"to": 2, "is": "stop", "why": "he cancels it"}')
    assert route.ask_the_model("cancela la mesa", procs)[::2] == (2, "stop")
    monkeypatch.setattr(llm, "chat_sync", lambda *a, **k: '{"to": 0, "is": "stop", "all": true, "why": "all"}')
    assert route.ask_the_model("para todo", procs)[2] == "stop_all"
    monkeypatch.setattr(llm, "chat_sync", lambda *a, **k: '{"to": 1, "is": "other", "all": true, "why": "x"}')
    assert route.ask_the_model("y que sea barato", procs)[2] == "other", "«all» means nothing outside a stop"


def test_disarm_a_stop_that_ends_nothing_is_not_reported_as_done(desk, monkeypatch):
    """The door refuses (the row had already ended): no line claims a stop, and Flash takes the turn."""
    _row("s1-6", "done", "Compare two phone plans")
    desk.procs = [_proc("s1-6", "Compare two phone plans", tid="9")]
    desk.model(1, "stop")
    assert _say(desk, "para eso") is False and desk.said == []
    monkeypatch.setattr(act, "stop", lambda procs: ["s1-6"])           # disarmed: the claim without the door
    monkeypatch.setattr(route, "stop", act.stop)
    assert _say(desk, "para eso ya") is True and desk.said == [_line("stopped_now")]


def test_the_stop_runs_on_the_loop_that_owns_the_sessions(desk, monkeypatch):
    """The turn decides on its own loop; the sessions live on the dispatcher's. The door is run THERE."""
    import threading
    _row("s1-7", "running", "Summarise the meeting")
    owner = asyncio.new_event_loop()
    t = threading.Thread(target=owner.run_forever, daemon=True)
    t.start()
    ran_on = []
    real = act._stop_here
    monkeypatch.setattr(act, "_stop_here", lambda procs: ran_on.append(asyncio.get_running_loop()) or real(procs))
    monkeypatch.setattr(dispatch, "_LOOP", owner)
    desk.procs = [_proc("s1-7", "Summarise the meeting")]
    desk.model(1, "stop")
    try:
        assert _say(desk, "déjalo, para") is True
    finally:
        owner.call_soon_threadsafe(owner.stop)
        t.join(timeout=2)
        owner.close()
    assert ran_on == [owner] and ts.task_get("s1-7")["state"] == "cancelled"


def test_the_turns_own_stop_ends_in_the_same_door_and_everything_closes_what_only_waits(desk, monkeypatch):
    """His stop that reaches Flash (`stop_worker`, the `stop_errand` verdict → `dispatch.cancel_soon`) ends in the SAME
    function as the switchboard's and the screen's button: the row's cancel door. «Everything» also closes a question
    that waits with no live session — the registry of sessions never listed it, so it used to stay open."""
    _row("s1-8", "running", "Search flights")
    _row("s1-9", "waiting", "Change the messaging widget")
    sess = _Session()
    dispatch._SESSIONS["8"] = SimpleNamespace(uid="s1-8", status="running", task_id="8", session=sess, task=None,
                                              settled="", trace_id="", label="", goal="Search flights", kind="web",
                                              result_summary="")
    from nucleo.cli import worker_api
    monkeypatch.setattr(worker_api, "open_asks", lambda: [{"task_id": "s1-9", "ask_id": "s1-9-a", "question": "?"}])

    async def go():
        monkeypatch.setattr(dispatch, "_LOOP", asyncio.get_running_loop())
        named = dispatch.cancel_soon("todo")
        await asyncio.sleep(0.05)
        return named
    assert asyncio.run(go()) == ["8", "s1-9"]
    assert [ts.task_get(u)["state"] for u in ("s1-8", "s1-9")] == ["cancelled", "cancelled"]
    assert sess.stops == ["operator"] and "8" not in dispatch._SESSIONS


def test_a_stop_of_one_named_thing_leaves_what_waits_alone(desk, monkeypatch):
    _row("s1-10", "waiting", "Book the table")
    from nucleo.cli import worker_api
    monkeypatch.setattr(worker_api, "open_asks", lambda: [{"task_id": "s1-10", "ask_id": "s1-10-a", "question": "?"}])

    async def go():
        monkeypatch.setattr(dispatch, "_LOOP", asyncio.get_running_loop())
        named = dispatch.cancel_soon("the flights search")
        await asyncio.sleep(0.05)
        return named
    assert asyncio.run(go()) == [] and ts.task_get("s1-10")["state"] == "waiting"


# ── a yes said before the question, and a send that was sent (V2-931, his test of 2026-11-18 01:23) ──────────────────
def test_his_go_ahead_while_the_send_is_being_prepared_is_the_yes_the_exit_door_takes(desk):
    """«OK, send it now» arrived while the worker was still redrafting: nothing was asked yet, so it was passed on as
    words, and the exit door then asked «shall I send it?». A yes said first is that yes: kept on the row, taken ONCE
    by the exit door; a later word that is not a yes takes it back; a task that is not a send keeps nothing."""
    from nucleo.workers import task_record
    _row("s2-1", "running", "Quiero que le mandes un mensaje a Quinn y le pongas dormidita.")
    ts.task_patch("s2-1", playbook="message")
    task_record.said("s2-1", "A ver, el mensaje que yo te había dicho es, espero que estés dormidita.")
    rec = SimpleNamespace(uid="s2-1")
    draft = {"widget_id": "mensajeria", "action": "draft", "payload": {"contact": "Quinn", "text": "Espero que estés dormidita."}}
    act.wrote(rec, "widget_data", draft)                        # the worker redrafts with HIS correction
    desk.procs = [_proc("s2-1", "Message to Quinn", tid="4")]
    desk.model(1, "yes")
    assert _say(desk, "vale, pues ahora mándalo") is True
    assert desk.said == [_line("send_going")] and desk.relayed == ["vale, pues ahora mándalo"]
    assert act.took_early_yes("s2-1") is True and act.took_early_yes("s2-1") is False, "it answers ONE question"
    assert _say(desk, "sí, mándalo ya") is True                 # given again …
    desk.model(1, "other")
    assert _say(desk, "espera, mejor pon buenas noches") is True      # … and taken back by a change
    assert act.took_early_yes("s2-1") is False
    desk.model(1, "yes")                                        # a text the AGENT composed is never covered by it
    assert _say(desk, "sí, mándalo") is True
    act.wrote(rec, "widget_data", {**draft, "payload": {"contact": "Quinn", "text": "Que descanses mucho, un abrazo."}})
    assert act.took_early_yes("s2-1") is False, "a yes said first covered words he never dictated"
    _row("s2-2", "running", "Compare three laptops")            # not a send: a yes with no question is only words
    desk.procs = [_proc("s2-2", "Compare three laptops", tid="5")]
    desk.model(1, "yes")
    assert _say(desk, "sí, adelante") is True and act.took_early_yes("s2-2") is False


def test_a_send_taken_to_its_receipt_is_never_judged_unmet_nor_relaunched(monkeypatch):
    """The session ended two seconds before the connector's receipt; its close read the goal «unmet» and relaunched the
    task on another model, which verified a sent message and said so again. The receipt is the verdict of a send the
    engine follows: the close steps aside."""
    from nucleo import circuit
    from nucleo.request import send_receipt
    launched = []
    monkeypatch.setattr("nucleo.acts.errand.escalate_to_slowbrain", lambda *a, **k: launched.append(a) or 1)
    monkeypatch.setattr(circuit, "verdict_of", lambda rec: ("unmet", "mensajeria.sent has no row"))
    monkeypatch.setattr(circuit, "_emit", lambda *a, **k: None)
    rec = SimpleNamespace(uid="s2-3", status="done", handoff="", task_id="9", goal="Message to Quinn", kind="generic",
                          trace_id="", done_when={}, depth=0, relay_gen=0, goal_retried=False, result_summary="", ok=True)
    monkeypatch.setitem(send_receipt._taken, "s2-3", time.time())
    assert circuit._close(rec, 3) == "skipped" and launched == [] and rec.verdict == "skipped"
    assert send_receipt.owns_the_verdict("s2-3") and not send_receipt.owns_the_verdict("nobody")


def test_plain_words_for_a_process_get_no_line_of_ours_the_process_speaks_next(desk):
    """01:23:49 — «Done, I'll keep it in mind for the message» after his correction, then the process's own new
    question: two lines for one thing. Words a process took are answered by the process (its question, its result)."""
    _row("s2-4", "running", "Message to Quinn")
    desk.procs = [_proc("s2-4", "Message to Quinn", tid="6")]
    desk.model(1, "other")
    assert _say(desk, "a ver, el mensaje es: espero que estés dormidita") is True
    assert desk.relayed == ["a ver, el mensaje es: espero que estés dormidita"] and desk.said == []
