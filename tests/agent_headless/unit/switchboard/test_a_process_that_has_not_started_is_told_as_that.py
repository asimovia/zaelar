"""A process that has not started is told as that, and the conversation is a candidate like any other (V2-935).

The tester's run on his engine (2026-11-18, 12:59–13:21, host saturated): a worker was held at the admission gate for
twenty minutes. The board listed it as running; «tell her I love her», said in answer to the assistant's own «what
shall I tell her?», went to that held contacts sync because it was the only entry of the list; each of four turns got
«got it»; «why is it taking so long?» was answered «I'm relaunching it» with nothing relaunched; and nobody told him
it had never begun.

  · the conversation with the assistant is entry 0 of the list the decision reads, with the assistant's last line;
  · a held process is listed as NOT STARTED; words it takes are kept and the line says so; «start it anyway» is the
    decision's `go`, which the gate obeys — held then by the memory floor only;
  · the pulse says a held errand has not begun (after 20 s, then at doubling intervals), never «still on it»;
  · the turn's own facts say NOT STARTED, never «stuck».

The judge is a double here (its quality is a bench's number: 26/32 → 33/34 on that run's turns); invented names.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from nucleo.switchboard import board, held, route

SYNC = {"key": "b0-1", "dispatch": "1", "title": "Sync the address book into the contacts card", "state": board.HELD,
        "question": "", "ask_id": "", "since": 0, "phase": "the voice goes first"}
RUNS = {**SYNC, "state": board.RUNNING, "phase": "reading"}


@pytest.fixture
def desk(monkeypatch):
    got = SimpleNamespace(injects=[], said=[], events=[], procs=[SYNC], rec=SimpleNamespace(held="waiting_voice", start_now=False))
    monkeypatch.setattr(board, "open_processes", lambda: [dict(p) for p in got.procs])
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "relay_his_words", lambda which, words: got.injects.append((which, words)) or True)
    monkeypatch.setattr(dispatch, "get_record", lambda tid: got.rec)
    monkeypatch.setattr(route, "_declared_answer", lambda text, procs: (None, ""))
    monkeypatch.setattr(route, "early_yes", lambda p, kind: False)
    monkeypatch.setattr(route, "_line", lambda key, about="": f"line:{key}")
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda *a, **k: None)
    route._seen.update(text="", key="", at=0.0)
    route._piece.update(text="", at=0.0)
    got.emit = lambda kind, label, text="", role="", extra=None: got.events.append(dict(extra or {}))
    got.model = lambda n, kind: monkeypatch.setattr(
        route, "ask_the_model", lambda text, procs, last="", before=None: (n, "double", kind))
    return got


def _take(desk, text):
    return asyncio.run(route.take(text, emit=desk.emit, say=desk.said.append))


# ── the list the decision reads ─────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("last, asked", [("¿Qué le digo a Quinn Ferrer?", True), ("What shall I tell Quinn?", True),
                                         ("Te abro los contactos.", False)])
def test_the_conversation_is_entry_zero_with_the_assistants_last_line(monkeypatch, last, asked):
    seen = []
    from nucleo.memory_agent.processor import llm
    monkeypatch.setattr(llm, "chat_sync", lambda seat, system, user, **k: seen.append(user) or '{"to": 0, "is": "talk"}')
    assert route.ask_the_model("dile que la quiero mucho", [SYNC], last)[0] == 0
    lines = seen[0].split("\n")
    assert lines[1].startswith("0. The CONVERSATION with the assistant itself") and last in lines[1]
    assert ("ASKED him" in lines[1]) is asked and lines[2].startswith("1. «Sync the address book")
    assert "NOT STARTED yet" in lines[2], "and a held process is listed as what it is"
    assert "Entry 0 is always the CONVERSATION" in route.SYSTEM and "even when that process is the only one open" in route.SYSTEM


def test_with_nothing_said_entry_zero_is_still_there():
    assert board.conversation_line("").startswith("0. The CONVERSATION") and "nothing said" in board.conversation_line("")


def test_the_board_lists_a_session_the_gate_holds_as_held(monkeypatch):
    from nucleo import dispatch
    from nucleo.cli import worker_api
    monkeypatch.setattr(worker_api, "open_asks", lambda: [])
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [
        {"id": "1", "request": "sync the address book", "phase": "the voice goes first", "held": "waiting_voice"},
        {"id": "2", "request": "find the film", "phase": "searching", "held": ""}])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: SimpleNamespace(uid=f"b0-{tid}", title=""))
    assert {p["key"]: p["state"] for p in board.open_processes()} == {"b0-1": board.HELD, "b0-2": board.RUNNING}


# ── his words for a held process ────────────────────────────────────────────────────────────────────────────────
def test_words_a_held_process_takes_are_kept_and_he_is_told_it_has_not_started(desk):
    desk.model(1, "other")
    assert _take(desk, "only the ones that have a phone") is True
    assert desk.injects == [("1", "only the ones that have a phone")], "kept on its record for when it starts"
    assert desk.said == [f"line:{held.KEPT}"], "never «got it, I'm on it» for something that has not begun"
    from nucleo import wording
    assert "NOT started" in wording.FACTS[held.KEPT] and "start it anyway" in wording.FACTS[held.KEPT]


def test_disarm_without_the_held_line_he_hears_on_it_about_work_that_never_began(desk, monkeypatch):
    desk.model(1, "other")
    monkeypatch.setattr(held, "line_key", lambda p, key: key)
    _take(desk, "only the ones that have a phone")
    assert desk.said == ["line:answer_taken"], "this is the «got it» the tester heard four times"


@pytest.mark.parametrize("said", ["arráncalo ya, no esperes más", "start it anyway"])
def test_his_start_it_anyway_lets_it_in_at_the_gate(desk, said):
    desk.model(1, held.GO)
    assert _take(desk, said) is True
    assert desk.rec.start_now is True and desk.injects == [], "the gate's mark, not words for the worker"
    assert desk.said == [f"line:{held.STARTING}"] and desk.events[-1]["is"] == held.GO


def test_a_go_for_a_process_that_already_runs_is_only_his_words_to_it(desk):
    desk.procs, desk.rec.held = [RUNS], ""
    desk.model(1, held.GO)
    assert _take(desk, "come on, get on with it") is True
    assert desk.rec.start_now is False and desk.injects == [("1", "come on, get on with it")]
    assert desk.said == ["line:answer_taken"]


def test_the_decision_reads_a_go(monkeypatch):
    from nucleo.memory_agent.processor import llm
    monkeypatch.setattr(llm, "chat_sync", lambda *a, **k: '{"to": 1, "is": "go", "why": "start now"}')
    assert route.ask_the_model("start it anyway", [SYNC])[::2] == (1, held.GO) and '"go"' in route.SYSTEM


# ── the gate ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_start_on_his_word_is_held_by_the_memory_floor_only(monkeypatch):
    from nucleo.workers import envelope
    monkeypatch.setattr(envelope, "admits", lambda *a: True)
    monkeypatch.setattr(envelope, "measured", lambda: (100, 50))
    monkeypatch.setattr(envelope, "host_stalled", lambda pol=None: True)
    monkeypatch.setattr(envelope, "shedding", lambda: True)
    assert envelope.reason() == "waiting_host" and envelope.reason(forced=True) == ""
    monkeypatch.setattr(envelope, "host_stalled", lambda pol=None: False)
    assert envelope.reason() == "waiting_voice" and envelope.reason(forced=True) == ""
    monkeypatch.setattr(envelope, "admits", lambda *a: False)
    assert envelope.reason(forced=True) == "waiting_room", "under the floor nothing starts, whoever asks"


def test_the_gate_lets_it_in_at_its_next_look_and_the_record_says_it_was_held(monkeypatch):
    from nucleo.dispatch import session as dsession
    from nucleo.workers import envelope
    monkeypatch.setattr(envelope, "admits", lambda *a: True)
    monkeypatch.setattr(envelope, "measured", lambda: (100, 50))
    monkeypatch.setattr(envelope, "host_stalled", lambda pol=None: False)
    monkeypatch.setattr(envelope, "shedding", lambda: True)
    rec = SimpleNamespace(held="", held_since=0.0, start_now=False)

    async def go():
        waiting = asyncio.ensure_future(envelope.wait_for_room(
            lambda why: held.mark(rec, why), key="1", runs=lambda: True, poll_s=0.01, forced=lambda: held.forced(rec)))
        await asyncio.sleep(0.05)
        assert not waiting.done() and rec.held == "waiting_voice" and rec.held_since > 0
        rec.start_now = True
        assert await asyncio.wait_for(waiting, 1.0) is True
    asyncio.run(go())
    envelope.released("1")
    import inspect
    src = inspect.getsource(dsession._a_slot)
    assert 'rec.held = ""' in src and "_h.mark(rec, why)" in src and "_h.forced(rec)" in src, \
        "the session marks the hold, reads his word and clears the mark when admitted"


# ── the pulse and the turn's facts ──────────────────────────────────────────────────────────────────────────────
def test_the_pulse_says_it_has_not_begun_then_at_doubling_intervals_never_still_on_it(monkeypatch):
    from nucleo.pulse import still_on_it as soi
    monkeypatch.setattr(soi, "_allowed", lambda: True)
    monkeypatch.setattr(soi, "_floor_free", lambda: True)
    soi._held_said.clear()
    s = {"id": "1", "uid": "b0-1", "title": "Sync the address book", "held": "waiting_voice", "held_s": 10,
         "status": "running", "waiting_on": "", "paused": False, "age_s": 10}
    assert soi.running([s]) == [], "a held errand is never «still on it»"
    assert soi.held_due([s], 1000.0) is None, "10 s held: not yet"
    s["held_s"] = 21
    assert soi.held_due([s], 1000.0) is s
    soi._held_said["b0-1"] = (1, 1000.0)
    assert soi.held_due([s], 1030.0) is None and soi.held_due([s], 1041.0) is s, "the second after 40 s more"
    soi._held_said["b0-1"] = (9, 1000.0)
    assert soi.held_due([s], 1000.0 + soi.HELD_MAX_S - 1) is None and soi.held_due([s], 1000.0 + soi.HELD_MAX_S) is s
    assert soi.held_due([], 2000.0) is None and soi._held_said == {}, "gone: forgotten"
    from nucleo import wording
    got = {}
    monkeypatch.setattr(wording, "word", lambda fact, **kw: got.update(fact=fact, **kw) or "x")
    soi.held_line(s, lambda key, **kw: {"still_held": "It hasn't started yet."}.get(key, ""))
    assert "NOT started" in got["fact"] and got["fallback"] == "It hasn't started yet."


def test_the_turns_facts_say_not_started_never_stuck(monkeypatch):
    from nucleo import dispatch
    from nucleo.turn.prompt import live_tasks
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [
        {"id": "1", "request": "sync the address book", "phase": "the voice goes first", "held": "waiting_voice",
         "secs": 1200, "silent_s": 1200, "pct": -1, "done": 0, "total": 0, "note": "", "no_step_s": 1200}])
    src = __import__("inspect").getsource(live_tasks)
    assert 'if t.get("held"):' in src and "NO HA EMPEZADO" in src
    assert src.index('if t.get("held"):') < src.index("ENCALLADA"), "read before any «stuck» fact"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_every_line_of_a_held_process_exists_in_his_language(lang):
    import json
    from pathlib import Path
    voice = json.loads((Path(__file__).resolve().parents[4] / "i18n" / "genesis" / lang / "voice.json").read_text())
    from nucleo import wording
    for key in (held.KEPT, held.STARTING, "still_held"):
        assert voice.get(key) and key in wording.FACTS, key
