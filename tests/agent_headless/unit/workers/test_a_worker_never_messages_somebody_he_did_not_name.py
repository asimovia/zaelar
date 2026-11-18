"""A worker never messages somebody he did not name: the send becomes a question — the message owner's (V2-938).

`best-plumber-same-day__es` (2026-10-14, sandbox 20261014-010939-es): he asked to FIND a well-rated plumber
who can come today. The brief the turn's model wrote said «Buscar y contactar fontaneros», and the worker
called `mensajeria send_to {to: 683139819, text: «Hola, ¿fontaneros de urgencia?…»}` twice. The door ALLOWED
it (`classify_act` → `action_mode_now` → FAST, because `send_to` is `confirm:false` for a turn executing his
order); only a missing directory entry stopped it.

Since V2-938 the question is not the worker's: the act is handed to the message owner (`nucleo/send`), which asks
him, sends on his yes and says the receipt (its own test: `unit/send/`). Here: nothing leaves from the worker.
"""
import asyncio
import json
import time

import pytest

from nucleo import his_words
from nucleo.cli import worker_api, worker_policy


class _Rec:
    task_id = "1"
    goal = "Buscar y contactar fontaneros de urgencia en Madrid centro con buenas valoraciones"
    waiting_on = ask = ask_corr = ""
    playbook_chosen = "errand"     # checkpoint 1 closed: the exit door now holds before every question (V2-852)

    def __init__(self):
        self.started = time.time()


@pytest.fixture
def door(monkeypatch):
    his_words.reset()
    rec = _Rec()
    ran: list = []

    async def _exec(action, payload, r):
        ran.append((action, payload))
        return {"ok": True}

    monkeypatch.setattr(worker_api, "_verify", lambda tid, tok: rec)
    monkeypatch.setattr(worker_api, "_piggyback", lambda tid: [])
    monkeypatch.setattr(worker_api, "_exec_allow", _exec)
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "get_record", lambda tid: rec)
    worker_api._ACTS.clear()
    from nucleo.pulse import notices
    from nucleo.send import draft, owner
    handed: list = []

    async def _intake(said, hint=None, **kw):
        handed.append(dict(hint or {}))
        return "¿Se lo mando?"

    async def _notify(*a, **kw):
        return {}
    monkeypatch.setattr(owner, "intake", _intake)
    monkeypatch.setattr(notices, "notify", _notify)
    rec.handed = handed
    yield rec, ran
    draft.reset()
    worker_api._ACTS.clear()
    his_words.reset()


def _act(payload):
    resp = asyncio.run(worker_api.worker_act(task_id="1", token="x", action="widget_data", payload=payload))
    return json.loads(resp.body)


_SEND = {"widget_id": "mensajeria", "action": "send_to",
         "payload": {"to": "683139819", "text": "Hola, ¿fontaneros de urgencia? Tengo una fuga…",
                     "objective": "Conseguir UN fontanero para HOY"}}


def test_the_premise_the_turn_has_and_the_worker_lacks():
    """The policy alone still allows it — the gate is what changes the answer, not the catalog."""
    assert worker_policy.classify_act("widget_data", _SEND) == worker_policy.ALLOW


def test_a_send_to_a_number_he_never_said_is_handed_to_the_owner_and_nothing_leaves(door):
    rec, ran = door
    his_words.note("Tengo una fuga en el baño y necesito un fontanero hoy sí o sí… uno que esté bien valorado")
    his_words.note("Madrid centro")
    out = _act(_SEND)
    assert (out.get("result") or {}).get("handed") is True, out
    assert ran == [], "the message left without his word"
    assert rec.handed and rec.handed[0]["to"] == "683139819", "the owner holds it, with the act's fields"
    assert worker_api.pending_asks() == [], "no second question on the worker's row"


def test_no_words_on_file_is_handed_too(door):
    """A restart, or a channel that never recorded the turn: not knowing what he said is not his yes."""
    rec, ran = door
    assert (_act(_SEND).get("result") or {}).get("handed") is True and ran == []
