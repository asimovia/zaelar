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




RUNS = {"key": "b0-2", "dispatch": "2", "title": "Delete the groups «Book club» and «Shopping list»",
        "state": "running", "question": "", "ask_id": "", "since": 0, "phase": "starting"}


def _judge(monkeypatch, answer: str):
    from nucleo.memory_agent.processor import llm
    monkeypatch.setattr(llm, "chat_sync", lambda *a, **k: answer)


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
    assert "_fold_into" not in src and "about_a_live_errand" not in src, \
        "nothing is folded at all any more (INI-078 S2): its own row coming back is never compared with another"
