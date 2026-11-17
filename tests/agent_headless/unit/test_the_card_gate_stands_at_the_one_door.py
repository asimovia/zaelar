"""CRIT-C4 at its door (V2-851 F4): building or rewriting a card of his asks first at `dispatch._run_session`, the one
door a worker is lit — whatever decides that the errand is card code.

Written BEFORE `nucleo/request/kind.py` lost its regexes (the file that was the criterion's only support): the
commission carries the brief's `errand_kind` verdict, so this holds with the old reader and the new one. The door
parks the question and starts no worker; an errand that is not card code passes the gate. Disarm: drop the gate and
a worker starts (`test_disarmed_the_door_lets_a_worker_start`).
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo import dispatch
from nucleo.dispatch import confirm as _dconf
from nucleo.workers.session_record import SessionRecord

COMMISSION = ("Modificar el widget `youtube` del operador en dos cosas concretas: rediseñar el HEADER de la app "
              "para que quede más bonito y limpio")
SURE = 0.95


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    dispatch._PENDING_CONFIRM.clear()
    dispatch._EXPIRED_CONFIRM.clear()
    monkeypatch.setattr(dispatch, "_deliver_confirm", lambda rec: asyncio.sleep(0))
    monkeypatch.setattr(dispatch, "_task_row", lambda *a, **k: None)
    monkeypatch.setattr(dispatch, "sync_state", lambda *a, **k: None)
    yield
    dispatch._PENDING_CONFIRM.clear()
    dispatch._EXPIRED_CONFIRM.clear()


def _run(req: str, verdict: str, monkeypatch) -> dict:
    """Run the door; `passed` is True when the errand went beyond the card gate (towards a worker)."""
    seen = {"passed": False}

    async def _beyond(task, key, req_):
        seen["passed"] = True
        return True                       # stop here: what lies beyond is not this test's

    monkeypatch.setattr(_dconf, "unlicensed_gate", _beyond)
    task = dispatch.Task(id="c4", request=req, kind="generic", trusted=True,
                         context={"errand_kind": {"choice": verdict, "confidence": SURE},
                                  "errand_class": {"choice": "none", "confidence": SURE}})
    dispatch._SESSIONS["c4"] = SessionRecord(task_id="c4", goal=req[:200], kind="generic")
    try:
        asyncio.run(dispatch._run_session(task))
    finally:
        dispatch._SESSIONS.pop("c4", None)
    return seen


def test_rewriting_a_card_of_his_parks_the_question_and_starts_no_worker(monkeypatch):
    seen = _run(COMMISSION, "change_card", monkeypatch)
    assert not seen["passed"], "a app of his was going to be rewritten without asking"
    p = dispatch.pending_confirm()
    assert p and p["task_id"] == "c4" and p["code_change"] == "modify" and p["question"]


def test_an_errand_that_is_not_card_code_passes_the_gate(monkeypatch):
    seen = _run("búscame vuelos a Roma para el jueves", "generic", monkeypatch)
    assert seen["passed"] and not dispatch.pending_confirm()


# ── a remark is not an order (V2-931, his rule of 2026-11-17) ────────────────────────────────────────────────────────
def _run_read(req: str, request_type: str, confidence: float, monkeypatch) -> tuple[dict, list]:
    """The same door, with the READING the commissioning turn carried (`brief.carried`)."""
    seen, rows = {"passed": False}, []

    async def _beyond(task, key, req_):
        seen["passed"] = True
        return True

    monkeypatch.setattr(_dconf, "unlicensed_gate", _beyond)
    monkeypatch.setattr(dispatch, "_task_row", lambda how, rec, **kw: rows.append((how, kw.get("state"))))
    reading = {"result": {"request_type": {"choice": request_type, "confidence": confidence}}, "open_ids": [],
               "turn_id": "T1", "judged": req}
    task = dispatch.Task(id="c5", request=req, kind="generic", trusted=True,
                         context={"errand_kind": {"choice": "change_card", "confidence": SURE},
                                  "errand_class": {"choice": "none", "confidence": SURE}, "reading": reading})
    dispatch._SESSIONS["c5"] = SessionRecord(task_id="c5", goal=req[:200], kind="generic")
    try:
        asyncio.run(dispatch._run_session(task))
        return seen, rows
    finally:
        dispatch._SESSIONS.pop("c5", None)


REMARK = ("Improve the messaging widget: when a message is sent it should show the connector's real delivery state "
          "instead of leaving it unconfirmed")


@pytest.mark.parametrize("request_type", ["comment", "complaint"])
def test_a_remark_builds_no_card_and_asks_nothing(request_type, monkeypatch):
    """23:09 — notes dictated for his developers, read `complaint`, were commissioned as «improve the messaging widget»
    and he was asked «shall I change your widget?». A remark starts no card work and parks no question."""
    seen, rows = _run_read(REMARK, request_type, 0.77, monkeypatch)
    assert not seen["passed"] and not dispatch.pending_confirm(), "a remark was asked about, or started a worker"
    assert rows == [("ended_early", "cancelled")] and "c5" not in dispatch._SESSIONS


def test_an_order_to_change_a_card_is_still_asked(monkeypatch):
    seen, rows = _run_read(COMMISSION, "order", 0.9, monkeypatch)
    p = dispatch.pending_confirm()
    assert not seen["passed"] and p and p["task_id"] == "c5" and p["code_change"] == "modify" and rows == []


def test_disarm_an_unread_reading_asks_as_before(monkeypatch):
    """With no sure reading the remark rule decides nothing: the gate asks (the safe side of this door)."""
    seen, _rows = _run_read(REMARK, "complaint", 0.2, monkeypatch)
    assert not seen["passed"] and dispatch.pending_confirm()
