"""A process that runs never owns the conversation (V2-935).

Measured on his engine (2026-11-18, 11:15–11:26). With ONE errand running, eight of his turns in four minutes — «you
are very slow», «stop repeating what I say», «why do you talk while I talk?» — were delivered to that errand as «a
complaint about the process» and nobody answered him. Three things made it possible, and each is pinned here:

  · the board named the errand by the sentence that commissioned it, which opened with a remark of his («no need to
    repeat what I say. Look, there is a group…») — the judge read every later remark as «about that task»;
  · the judge had no way to say «this is for the assistant itself»: a complaint was a process's by instruction;
  · words a process took got no line of ours, so a wrong delivery was total silence.

And one errand was lost on the way: his answer to a worker's question resumed its session, the dispatcher's dedup
folded that resume «by widget» into ANOTHER live errand, and the row stayed running with nobody behind it.

The judge is a double here (its quality is a bench's number); invented people, ES and EN.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from nucleo.switchboard import board, route

RUNS = {"key": "b0-2", "dispatch": "2", "title": "Delete the groups «Book club» and «Shopping list»",
        "state": "running", "question": "", "ask_id": "", "since": 0, "phase": "starting"}


@pytest.fixture
def desk(monkeypatch):
    got = SimpleNamespace(injects=[], said=[], events=[], procs=[RUNS])
    monkeypatch.setattr(board, "open_processes", lambda: [dict(p) for p in got.procs])
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "relay_his_words", lambda which, words: got.injects.append((which, words)) or True)
    monkeypatch.setattr(route, "_declared_answer", lambda text, procs: (None, ""))
    monkeypatch.setattr(route, "early_yes", lambda p, kind: False)
    monkeypatch.setattr(route, "_line", lambda key, about="": f"line:{key}")
    route._seen.update(text="", key="", at=0.0)
    route._piece.update(text="", at=0.0)
    got.emit = lambda kind, label, text="", role="", extra=None: got.events.append(dict(extra or {}))
    return got


def _take(desk, text):
    return asyncio.run(route.take(text, emit=desk.emit, say=desk.said.append))


def _judge(monkeypatch, answer: str):
    from nucleo.memory_agent.processor import llm
    monkeypatch.setattr(llm, "chat_sync", lambda *a, **k: answer)


@pytest.mark.parametrize("said", ["vas muy lento en todo, te estoy hablando y te quedas ahí parado",
                                  "stop repeating what I say", "why do you talk while I am talking?"])
def test_words_for_the_assistant_itself_are_nobodys_whatever_number_the_judge_gave(desk, monkeypatch, said):
    """11:22:21 — the judge's own reason read «complaint about slowness / no response, not a decision on the message»
    and its number was 1. It now has a word for that, and that word is nobody's."""
    _judge(monkeypatch, '{"to": 1, "is": "talk", "why": "complaint about the assistant\'s manner"}')
    assert route.ask_the_model(said, [RUNS])[0] == 0
    assert _take(desk, said) is False, "Flash takes the turn and answers him"
    assert desk.injects == [] and desk.said == [], "the errand gets nothing, and no line of ours stands in for a reply"
    assert desk.events[-1]["to"] == "" and desk.events[-1]["event"] == "switchboard"
    assert '"talk"' in route.SYSTEM and "never owns the conversation" in route.SYSTEM


def test_disarm_without_the_talk_kind_the_errand_swallows_his_complaint(desk, monkeypatch):
    _judge(monkeypatch, '{"to": 1, "is": "talk", "why": "complaint about the assistant\'s manner"}')
    monkeypatch.setattr(route, "TALK", "—")
    assert _take(desk, "you are very slow at everything") is True and desk.injects, "this is the swallowed turn"


@pytest.mark.parametrize("said", ["que esté enamorado de mí también", "take that last sentence out"])
def test_what_is_about_a_running_errands_matter_reaches_it_and_he_is_answered_at_once(desk, monkeypatch, said):
    """Who, which one, what text: the errand's worker owns it — and he hears one short line now, not in a minute."""
    _judge(monkeypatch, '{"to": 1, "is": "other", "why": "changes the text"}')
    assert _take(desk, said) is True
    assert desk.injects == [("2", said)] and desk.said == ["line:answer_taken"]


def test_disarm_a_delivery_with_no_line_is_silence(desk, monkeypatch):
    _judge(monkeypatch, '{"to": 1, "is": "other", "why": "changes the text"}')
    monkeypatch.setattr(route, "_line", lambda key, about="": "")
    assert _take(desk, "take that last sentence out") is True and desk.said == [], "the line is what breaks the silence"


def test_the_board_names_a_running_errand_by_what_it_does_not_by_his_sentence(monkeypatch):
    """11:19:35 — his turn was «OK, no need to repeat what I say. Look, there is a group…»; the errand was named
    «Delete the groups …» one second later, and the board kept showing his sentence."""
    from nucleo import dispatch
    from nucleo.cli import worker_api
    monkeypatch.setattr(worker_api, "open_asks", lambda: [])
    heard = "OK, no need to repeat what I say. Look, there is a group called Book club, delete it"
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [
        {"id": "2", "request": "In his messaging there is a group called «Book club»: delete it", "heard": heard, "phase": ""},
        {"id": "3", "request": "find the film", "heard": "", "phase": ""}])
    recs = {"2": SimpleNamespace(uid="b0-2", title="Delete the group «Book club»"), "3": SimpleNamespace(uid="b0-3", title="")}
    monkeypatch.setattr(dispatch, "get_record", lambda tid: recs[str(tid)])
    got = {p["key"]: p["title"] for p in board.open_processes()}
    assert got == {"b0-2": "Delete the group «Book club»", "b0-3": "find the film"}
    assert "repeat" not in board.line(1, {**RUNS, "title": got["b0-2"]})
    recs["2"].title = ""            # not named yet: its brief, still not his sentence
    assert board.open_processes()[0]["title"].startswith("In his messaging")


def test_a_session_resumed_by_his_answer_is_its_row_and_is_compared_with_nothing():
    """11:20:44 — «then tell me which ones you have», his answer to «which one do I send it to?», resumed the send's
    session; the dedup matched it «by widget» with the group errand and folded it in. The row stayed running with no
    session and vanished from the board, so the next four questions about that send had nobody to go to."""
    import inspect

    from nucleo.cli import worker_api_resume
    from nucleo.dispatch import listener
    row = {"id": "b0-i3", "kind": "generic", "playbook": "message", "goal": "Message to Quinn", "session_id": "native-1"}
    ctx = worker_api_resume.context_for(row, {"question": "Which one?", "answer": "tell me which ones you have"})
    assert (ctx.get("resume") or {}).get("rebrief"), "an answered resume carries its re-brief"
    src = inspect.getsource(listener)
    assert '_bound = bool(ctx.get("answers") or (ctx.get("resume") or {}).get("rebrief"))' in src
    assert "if not dup and not _bound" in src and '("", {}) if _bound else _d.dedup_scan' in src, \
        "a bound launch skips both halves of the dedup"
