"""A clarification ends with its conversation (V2-886 D1, second half): answered, moved on, or expired.

A clarify (a fact or a choice the work needs) is dialogue: it never outlives the conversation that asked it. When his
next turn surely answers none of the waiting questions (the binding verdict `none` at VETO) a clarify our last reply put
closes — by its id (`circuit.asked_last`), never by its words; one left unanswered past `clarify_wait_minutes` is closed
by the pulse. Each close cancels its row (a parked worker is told) and says so in ONE `ask_closed` event — no line, never
re-asked. A consent question is not a clarify: it keeps its card and its days. Disarm: `moved_on` without the asked-id
check, `expired` with no kind check, the close with no event → red.
"""
from __future__ import annotations

import threading
import time

import pytest

from nucleo.circuit import asked_last, asker, ledger
from nucleo.cli import worker_api_bind as B
from nucleo.request import clarify_end as CE


def _row(question: str, consent: str) -> tuple[str, str]:
    uid = asker.open_row(question, kind="generic", visible=False)
    ask_id = f"{uid}-q1"
    asker.ask(uid, {"ask_id": ask_id, "question": question, "consent": consent, "inline": True,
                    "retained": {"kind": "x"}})
    return uid, ask_id


def _brief(choice: str, conf: float) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t", "judged": "x",
            "result": {B.KEY: {"choice": choice, "confidence": conf, "probs": {choice: conf}}}}


def _state(uid: str) -> str:
    return str((ledger.store().task_get(uid) or {}).get("state") or "")


@pytest.fixture
def events():
    seen = []
    return seen, lambda kind, label, text="", role="", extra=None, **k: seen.append((label, extra or {}))


def test_a_clarify_our_last_reply_put_closes_when_he_moves_on(events):
    seen, emit = events
    clar, clar_ask = _row("¿Poner qué?", "ask_fact")
    cons, _ = _row("¿Envío el correo a Marta?", "ask_consent")
    asked_last.turn_began()                                   # his next turn begins: our last reply asked these
    assert CE.moved_on(_brief(B.NONE, 0.9), emit) == [clar_ask]
    assert _state(clar) == "cancelled" and _state(cons) == "waiting", "a consent question closed as a clarification"
    assert [x for _l, x in seen if x.get("kind_diag") == CE.EV] == [
        {"kind_diag": CE.EV, "task_id": clar, "ask_id": clar_ask, "reason": CE.MOVED_ON}]


def test_a_doubt_or_an_old_clarify_is_not_closed_by_a_new_turn(events):
    seen, emit = events
    clar, _ = _row("¿Poner qué?", "ask_fact")
    asked_last.turn_began()
    assert CE.moved_on(_brief(B.NONE, 0.7), emit) == [], "a doubt closed the clarification"
    asked_last.turn_began(object())                           # a reply of ours since that asked nothing
    assert CE.moved_on(_brief(B.NONE, 0.95), emit) == [] and _state(clar) == "waiting", \
        "a clarify our LAST reply did not put was closed (its deadline ends it, not his turn)"


def test_an_unanswered_clarify_expires_silently_and_a_consent_keeps_its_days(events):
    seen, _emit = events
    clar, _ = _row("¿Cuál de las dos?", "ask_which")
    cons, _ = _row("¿Borro la cita?", "ask_consent")
    later = time.time() + CE.wait_s() + 5
    closed = CE.expired(later)                               # (the suite's store may hold other tests' rows)
    assert clar in closed and cons not in closed
    assert _state(clar) == "cancelled" and _state(cons) == "waiting"
    assert clar not in CE.expired(later), "an expired clarify closed twice"


def test_an_answered_clarify_is_no_longer_waiting_and_nothing_closes_it(events):
    seen, emit = events
    clar, clar_ask = _row("¿Poner qué?", "ask_fact")
    ledger.resumed(clar)                                      # his answer took it: the row works again
    asked_last.turn_began()
    assert CE.moved_on(_brief(B.NONE, 0.9), emit) == [] and _state(clar) == "running"
