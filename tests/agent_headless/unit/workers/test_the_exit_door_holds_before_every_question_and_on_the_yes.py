"""A worker's act that leaves crosses its exit door before ANY question (V2-852, CRIT-T2b; V2-931).

The act's own refusal was only read by an inline confirmation Flash no longer opens for a send, so a worker could be
asked about a reply that answers nothing. Now the door holds first — the act's own refusal
(`widgets.contract.would_refuse`) — then the one question is asked, and his yes runs the retained act. ES and EN.

Since V2-938 the question about a MESSAGE is its owner's (`nucleo/send`): the door's refusal still comes first, and
what it would have asked is handed to the owner with nothing sent.
"""
from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from nucleo import his_words, untrusted


@pytest.fixture
def door(monkeypatch):
    from nucleo.cli import worker_api, worker_api_answer
    from widgets import server_api
    untrusted.reset()
    his_words.reset()
    sent = []

    async def _brain_action(wid, act, payload):
        sent.append((wid, act, dict(payload)))
        return {"ok": True}
    monkeypatch.setattr(server_api, "brain_action", _brain_action)
    monkeypatch.setattr(worker_api, "classify_act", lambda *_a: worker_api.ALLOW)
    monkeypatch.setattr(worker_api, "_piggyback", lambda *_a: [])
    monkeypatch.setattr(worker_api_answer, "_says_yes", lambda *_a: True)
    rec = SimpleNamespace(task_id="xd", playbook_chosen="errand", uid="", started=time.time(), depth=0, trace_id="",
                          surface="", sheet="", native_sid="", waiting_on="", ask="", ask_corr="", parked=False,
                          mandate={})
    monkeypatch.setattr(worker_api, "_verify", lambda *_a: rec)
    monkeypatch.setattr(worker_api_answer, "_record_for", lambda _e: rec)
    worker_api._ACTS.clear()
    from nucleo.pulse import notices
    from nucleo.send import owner
    handed = []

    async def _intake(said, hint=None, **kw):
        handed.append(dict(hint or {}))
        return "?"

    async def _notify(*a, **kw):
        return {}
    monkeypatch.setattr(owner, "intake", _intake)
    monkeypatch.setattr(notices, "notify", _notify)
    yield SimpleNamespace(api=worker_api, rec=rec, sent=sent, handed=handed)
    worker_api._ACTS.clear()
    untrusted.reset()
    his_words.reset()


def _asked(d) -> bool:
    return any(e.get("state") == "pending" for e in d.api._ACTS.values())


def _act(d, action="send_to", payload=None):
    out = asyncio.run(d.api.worker_act(task_id="xd", token="t", action="widget_data", payload={
        "widget_id": "mensajeria", "action": action,
        "payload": payload if payload is not None else {"to": "+34600999888", "text": "¿tenéis cita?",
                                                        "platform": "whatsapp"}}))
    return json.loads(out.body)


# ── H4 · the one question, and his yes ───────────────────────────────────────────────────────────────────────────

def test_with_checkpoint_one_closed_the_unnamed_recipient_is_handed_to_the_owner(door):
    his_words.note("find a plumber in Madrid and book")
    got = _act(door)
    assert (got.get("result") or {}).get("handed") is True and door.sent == [] and not _asked(door), got
    assert door.handed and door.handed[0]["to"] == "+34600999888"


# ── H5 · a call the act would refuse is never asked about ──────────────────────────────────────────────────────

@pytest.mark.parametrize("said", ["contesta a Raquel que la esperamos", "reply to Raquel that we're waiting"])
def test_a_reply_that_answers_nothing_is_refused_at_the_door_before_any_question(door, said):
    his_words.note(said)
    got = _act(door, "reply", {"text": "Te esperamos en casa."})
    assert got.get("ok") is False and "would be refused" in str(got.get("error")), got
    assert door.sent == [] and not _asked(door)


def test_disarmed_the_acts_refusal_is_asked_about(door, monkeypatch):
    from widgets import contract
    monkeypatch.setattr(contract, "would_refuse", lambda *_a: None)
    his_words.note("reply to Raquel that we're waiting")
    got = _act(door, "reply", {"text": "Te esperamos en casa."})
    assert got.get("status") == "pending" or got.get("ok"), "the disarm did not take"


def test_the_yes_after_the_worker_ended_reads_checkpoint_one_from_the_row(monkeypatch):
    """Live, 2026-11-05: the worker named its playbook, recorded its goal, asked, and ENDED; his «sí» rebuilt the
    record from the row without either, so the exit door read checkpoint 1 as open and refused the send he had just
    confirmed — a second worker had to start. The stand-in carries the row's playbook and its spec's end state."""
    from nucleo import dispatch
    from nucleo.circuit import ledger, spec
    from nucleo.cli import worker_api_answer
    from nucleo.workers.prompts import playbook
    monkeypatch.setattr(dispatch, "get_record", lambda _tid: None)
    store = SimpleNamespace(task_get=lambda uid: {"playbook": "message", "kind": "generic", "goal": "send it"})
    monkeypatch.setattr(ledger, "store", lambda: store)
    dw = {"widget": "mensajeria", "collection": "sent", "where": {"name": "Quinn"}}
    monkeypatch.setattr(spec, "of_task", lambda tid: {"done_when": dw} if tid == "t9" else None)
    rec = worker_api_answer._record_for({"task_id": "t9", "uid": "u9"})
    assert playbook.checkpoint_one(rec) == "", "the row closed checkpoint 1; the yes must not reopen it"
    monkeypatch.setattr(store, "task_get", lambda uid: {})          # disarm: a row with no playbook stays open
    assert playbook.checkpoint_one(worker_api_answer._record_for({"task_id": "t9", "uid": "u9"}))


def test_a_live_record_that_lost_its_end_state_reads_it_from_the_task(monkeypatch):
    """The same refusal, measured again on b110: the live record survived the worker's turn but its end state did not —
    checkpoint 1 is read from what the TASK keeps, so any path to the door sees the same closed checkpoint."""
    from nucleo.circuit import ledger, spec
    from nucleo.workers.prompts import playbook
    monkeypatch.setattr(ledger, "store", lambda: SimpleNamespace(task_get=lambda uid: {"playbook": "message"}))
    monkeypatch.setattr(spec, "of_task", lambda tid: {"done_when": {"widget": "mensajeria"}} if tid == "t1" else None)
    rec = SimpleNamespace(task_id="t1", uid="u1", playbook_chosen="message", done_when={})
    assert playbook.checkpoint_one(rec) == ""
    monkeypatch.setattr(spec, "of_task", lambda tid: None)        # disarm: nothing durable, the checkpoint stays open
    assert playbook.checkpoint_one(rec)
