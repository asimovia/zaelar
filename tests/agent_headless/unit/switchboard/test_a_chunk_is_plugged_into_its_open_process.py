"""Every chunk he says is plugged into the open process it belongs to, by ONE decision, before Flash runs (V2-931).

Measured on his engine (2026-11-17): 44 of 44 routing decisions on a session with a task WAITING on him read «new» with
an empty menu (the router only saw worker errands), his explicit yes was read at 0.04, and the small model re-called
the act five times. The switchboard reads one board — what runs and what waits, whoever asked — and delivers the chunk
itself: a waiting question takes it as its answer, a running worker as his next words; anything else is Flash's turn.

The same decision says what KIND of reply it is to a process that waits on his yes: a plain yes or no decides its
retained act at once, as the screen's button does, and he hears ONE line; a cut-off piece is held and joined to what he
says next; anything else resumes the process with his words.

The model is a double here (the decision's quality is a bench's number, not a unit's): what these pin is the board, the
decisions made by identity, the delivery, the line and the record. ES and EN, invented people.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from nucleo.switchboard import board, route

WAITS = {"key": "b0-7", "dispatch": "", "title": "mándale un mensaje a Quinn diciendo que llegamos tarde",
         "state": "waiting", "question": "The message is ready. Shall I send it to Quinn Ferrer?", "ask_id": "q1",
         "since": 10}
RUNS = {"key": "b0-9", "dispatch": "9", "title": "find a short film called The Pumpkin", "state": "running",
        "question": "", "ask_id": "", "since": 0, "phase": "searching"}


@pytest.fixture
def desk(monkeypatch):
    got = SimpleNamespace(answers=[], injects=[], events=[], said=[], asked=[], procs=[])
    monkeypatch.setattr(board, "open_processes", lambda: [dict(p) for p in got.procs])
    from nucleo.cli import worker_api
    from nucleo import dispatch
    got.choices = []
    monkeypatch.setattr(worker_api, "answer_soon", lambda ask, text, choice=None: (
        got.answers.append((ask, text)), got.choices.append(choice)) and True)
    monkeypatch.setattr(dispatch, "relay_his_words", lambda which, words: got.injects.append((which, words)) or True)
    monkeypatch.setattr(route, "_declared_answer", lambda text, procs: (None, ""))
    monkeypatch.setattr(route, "waits_on_his_yes", lambda p: p["state"] == "waiting")
    monkeypatch.setattr(route, "line_of", lambda p, kind: f"line:{kind}")
    route._seen.update(text="", key="", at=0.0)
    route._piece.update(text="", at=0.0)
    got.emit = lambda kind, label, text="", role="", extra=None: got.events.append({"kind": kind, "label": label, **(extra or {})})
    got.model = lambda n, kind="other": monkeypatch.setattr(
        route, "ask_the_model", lambda text, procs, last="", before=None: got.asked.append(text) or (n, "double", kind))
    return got


def _take(desk, text):
    return asyncio.run(route.take(text, emit=desk.emit, say=desk.said.append))


def test_with_nothing_open_nothing_is_asked_and_flash_takes_the_turn(desk):
    desk.model(1)
    assert _take(desk, "open YouTube") is False
    assert desk.asked == [] and desk.events == [], "an empty board costs no model call and decides nothing"


@pytest.mark.parametrize("said", ["Vale, mi respuesta es que sí, pero precisamente ese mensaje", "yes go on, send exactly that"])
def test_his_answer_to_a_waiting_question_reaches_it_as_he_said_it(desk, said):
    desk.procs, _ = [WAITS], desk.model(1)
    assert _take(desk, said) is True
    assert desk.answers == [("q1", said)] and desk.injects == [] and desk.choices == [None]
    ev = desk.events[-1]
    assert (ev["kind"], ev["event"], ev["to"], ev["by"], ev["delivered"]) == ("thread", "switchboard", "b0-7", "model", True)
    assert ev["board"] and "WAITING" in ev["board"][0], "the record carries the board the decision read"
    assert desk.said == ["line:other"], "one short line tells him his words were taken"


def test_a_detail_for_a_running_worker_is_injected_into_it(desk):
    desk.procs, _ = [WAITS, RUNS], desk.model(2)
    assert _take(desk, "it is only pumpkin, not pumpkin curry") is True
    assert desk.injects == [("9", "it is only pumpkin, not pumpkin curry")] and desk.answers == []


@pytest.mark.parametrize("said", ["abre YouTube", "what's the weather tomorrow?"])
def test_what_is_for_no_process_is_flashs_turn_and_is_recorded(desk, said):
    desk.procs, _ = [WAITS], desk.model(0)
    assert _take(desk, said) is False
    assert desk.answers == [] and desk.injects == [] and desk.said == []
    assert desk.events[-1]["to"] == "" and desk.events[-1]["label"].endswith("(for no open process)")


def test_an_unreadable_or_late_decision_never_swallows_his_words(desk, monkeypatch):
    desk.procs, _ = [WAITS], desk.model(-1)
    assert _take(desk, "send it") is False and desk.answers == []
    monkeypatch.setattr(route, "DECIDE_S", 0.05)
    monkeypatch.setattr(route, "ask_the_model", lambda *a, **k: __import__("time").sleep(0.4) or (1, "late", "other"))
    assert _take(desk, "send it now") is False and desk.events[-1]["by"] == "timeout"


def test_a_sentence_handed_again_as_it_grows_delivers_only_what_is_new(desk):
    """The ear hands «…send it» and then «…send it, exactly that text»: the process gets each word once."""
    desk.procs, _ = [RUNS], desk.model(1)
    assert _take(desk, "It is from 2022") is True
    assert _take(desk, "It is from 2022") is True, "the same chunk again is already there: nothing new travels"
    assert _take(desk, "It is from 2022, the animated one") is True
    assert desk.injects == [("9", "It is from 2022"), ("9", "the animated one")]
    assert len(desk.asked) == 1, "the continuation follows its sentence: no second decision"


def test_the_only_waiting_questions_declared_answer_needs_no_model(desk, monkeypatch):
    """«Sí» / «No» — the words of the row's own two buttons — go to the ONE question that waits, by identity."""
    desk.procs, _ = [WAITS], desk.model(0)
    from nucleo.circuit import asker
    monkeypatch.setattr(asker, "artefact", lambda uid: {"options": ["Yes", "No"]})
    monkeypatch.setattr(route, "_declared_answer", _real_declared)
    assert _take(desk, "Yes.") is True
    assert desk.answers == [("q1", "Yes.")] and desk.asked == [] and desk.events[-1]["by"] == "declared"
    assert desk.choices == [0] and desk.said == ["line:yes"], "the declared yes decides the act, as the button does"


def test_two_waiting_questions_are_never_answered_by_identity(desk, monkeypatch):
    other = {**WAITS, "key": "b0-8", "ask_id": "q2", "since": 20}
    desk.procs, _ = [WAITS, other], desk.model(2)
    monkeypatch.setattr(route, "_declared_answer", _real_declared)
    assert _take(desk, "yes") is True
    assert desk.answers == [("q2", "yes")] and desk.asked == ["yes"], "with two waiting, the decision names which"


def test_the_board_is_one_list_of_what_runs_and_what_waits(monkeypatch):
    """A row waiting on his answer and a live session are the same list; a live session that asked is ONE process."""
    from nucleo import dispatch
    from nucleo.cli import worker_api
    monkeypatch.setattr(worker_api, "open_asks", lambda: [
        {"task_id": "b0-7", "ask_id": "q1", "question": "Send it?", "title": "message to Quinn", "since": 10},
        {"task_id": "b0-i2", "ask_id": "q3", "question": "Delete it?", "title": "delete the note", "since": 5}])
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [
        {"id": "4", "request": "message to Quinn", "phase": ""}, {"id": "9", "request": "find the film", "phase": "searching"}])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: SimpleNamespace(uid={"4": "b0-7", "9": "b0-9"}[str(tid)]))
    got = board.open_processes()
    assert [(p["key"], p["state"], p["dispatch"]) for p in got] == [
        ("b0-9", "running", "9"), ("b0-i2", "waiting", ""), ("b0-7", "waiting", "4")]
    assert "WAITING for his answer to: «Send it?»" in board.line(1, got[2])


_real_declared = route._declared_answer


@pytest.mark.parametrize("said, kind, choice", [("Puedes mandar el mensaje, te autorizo", "yes", 0),
                                                ("send it, go ahead", "yes", 0),
                                                ("no, déjalo, no lo mandes", "no", 1)])
def test_a_plain_yes_or_no_decides_the_waiting_act_at_once(desk, said, kind, choice):
    """His yes in any wording is the button's yes: the retained act is decided now, no session is resumed to read it."""
    desk.procs, _ = [WAITS], desk.model(1, kind)
    assert _take(desk, said) is True
    assert desk.answers == [("q1", said)] and desk.choices == [choice]
    assert desk.said == [f"line:{kind}"] and desk.events[-1]["is"] == kind


def test_a_yes_to_a_question_that_holds_no_act_is_only_his_words(desk, monkeypatch):
    """«Sí» to «which Quinn?» decides nothing: a question that retained no act takes his words as they are."""
    desk.procs, _ = [WAITS], desk.model(1, "yes")
    monkeypatch.setattr(route, "waits_on_his_yes", lambda p: False)
    assert _take(desk, "yes, the first one") is True
    assert desk.choices == [None] and desk.said == ["line:other"]


def test_a_cut_off_piece_is_held_and_joined_to_what_he_says_next(desk):
    """Measured 2026-11-17 23:06: «mensaje.» and then «…puedes mandar el mensaje.» — the piece resumed the task and was
    answered twice. A piece that says nothing yet is delivered to nobody and acknowledged by nothing."""
    desk.procs, _ = [WAITS], desk.model(1, "fragment")
    assert _take(desk, "mensaje.") is True
    assert desk.answers == [] and desk.said == [] and desk.events[-1]["delivered"] is False
    desk.model(1, "yes")
    assert _take(desk, "puedes mandar el mensaje.") is True
    assert desk.answers == [("q1", "mensaje. puedes mandar el mensaje.")] and desk.choices == [0]
    assert desk.said == ["line:yes"], "ONE line for the whole sentence"


def test_a_held_piece_is_forgotten_after_its_window(desk, monkeypatch):
    desk.procs, _ = [WAITS], desk.model(1, "fragment")
    assert _take(desk, "bueno,") is True
    route._piece["at"] -= route.PIECE_S + 1
    desk.model(0)
    assert _take(desk, "abre YouTube") is False and desk.asked[-1] == "abre YouTube"


def test_the_line_he_hears_is_the_sends_own(monkeypatch):
    from i18n import langs
    from nucleo.circuit import asker
    from nucleo.request import send_receipt as send_errand
    lang = langs.current_language()
    monkeypatch.setattr(asker, "artefact", lambda uid: {"retained": {"action": "widget_data"}})
    monkeypatch.setattr(send_errand, "is_send", lambda retained: True)
    assert _real_line(WAITS, "yes") == lang.send_going and _real_line(WAITS, "no") == lang.send_not_sent
    monkeypatch.setattr(send_errand, "is_send", lambda retained: False)
    assert _real_line(WAITS, "yes") == lang.work_started and _real_line(WAITS, "no") == lang.confirm_cancelled
    assert _real_line(RUNS, "other") == lang.answer_taken and "tarea" not in langs.spec("es").answer_taken


_real_line = route.line_of


def test_disarmed_a_delivery_that_fails_is_not_called_taken(desk, monkeypatch):
    """Disarm: with `deliver` returning False the chunk must fall to Flash — seen red when `take` ignores it."""
    desk.procs, _ = [WAITS], desk.model(1)
    monkeypatch.setattr(route, "deliver", lambda p, text: False)
    assert _take(desk, "send it") is False and desk.events[-1]["delivered"] is False
