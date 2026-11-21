"""An errand is born IN its turn, with his whole request (V2-844 F1a, 2026-11-02).

A car request dictated in fragments: the turn that finally launched it had «Okay.» as its own words, its cut sentence
joined in front of it only for the verdict. The listing door handed the worker `operator_text or query` — the
fragment — and the errand that survived was called «Okay.». Its durable row only appeared when the dispatcher picked
the escalation up, so until then the turn's sheet and launches belonged to nobody, under a counter id of their own.

Now an errand is born where the turn decides it: a durable row (`starting`, off the board) with its uid, which also
names its sheet, and with the WHOLE request the turn's verdict judged. The dispatcher adopts that row; a delivery at
the first rung closes it; a launch folded into another errand or refused leaves nothing behind.
"""
from __future__ import annotations

import asyncio

import pytest

from memory import db as memdb, tasks_store as ts
from nucleo.acts import errand, search_sheet
from nucleo.circuit import ledger
from nucleo import turn_marks
from voice import trace

CAR_EN = ("let's focus on the car. I wanna... One of those big runners, a Toyota 4Runner. Two or three good offers. "
          "Thirty, forty, fifty thousand. Okay.", "Okay.")
CAR_ES = ("vale, el coche. Uno de esos todoterreno grandes, un Toyota 4Runner. Dos o tres buenas ofertas. Entre treinta "
          "y cincuenta mil. Vale.", "Vale.")
FLAT_EN = ("find me a flat to rent in Madrid, two bedrooms, near Retiro, under fifteen hundred. Right.", "Right.")


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    memdb.reset_db()
    memdb.get_db()
    errand.reset()
    turn_marks.reset()
    from nucleo.workers import ended as _ended
    _ended._LISTING_DELIVERIES.clear()
    yield
    errand.rows_settled()
    _ended._LISTING_DELIVERIES.clear()      # a delivery is shared state: it must not outlive the test that made it
    turn_marks.reset()
    trace.adopt("")
    memdb.reset_db()
    errand.reset()


def _rows() -> list[dict]:
    errand.rows_settled()
    return ts.tasks_where(states=(*ts.LIVE_STATES, *ts.DONE_STATES, ledger.STARTING), visible_only=False, limit=50)


# ── the request is the whole one ────────────────────────────────────────────────────────────────────────────

# ── the listing door: born before the pass, the whole request, the uid is the sheet ───────────────────────────

@pytest.fixture
def pass_rig(db, monkeypatch):
    sent: list = []
    written: list = []

    def _write(sid, title, items, *a, **k):
        written[:] = items

    # No sheet is written here, so the rig says what it would hold: every row kept (V2-879 O3 reads the sheet).
    monkeypatch.setattr(search_sheet, "_write_sheet", _write)
    monkeypatch.setattr(search_sheet, "_held", lambda sid: {"state": "kept" if written else "none",
                                                           "kept": len(written), "rejected": 0, "rows": list(written)})
    monkeypatch.setattr(search_sheet, "_observe", lambda *a, **k: None)
    monkeypatch.setattr(errand, "_emit_bus", lambda topic, payload: sent.append(payload))
    monkeypatch.setattr("nucleo.consequence.passes", lambda *a, **k: True)
    found = {"items": [], "needs_browser": True}
    monkeypatch.setattr("search.listing.search", lambda q: {"sources": [], **found})
    return sent, found


# ── the portal: every escalation is born; a relay continues its own row ─────────────────────────────────────

def test_a_relay_continues_its_row_and_is_not_born_again(pass_rig):
    sent, _ = pass_rig
    errand.escalate_to_slowbrain("find me a flat in Madrid", context={"kind": "web", "task_uid": "b0-1"})
    assert not _rows() and "born_uid" not in sent[0]["context"]


# ── the dispatcher adopts the row; a fold or a halt leaves nothing behind; nobody adopting it, the pulse does ──

def _listen(monkeypatch, request, ctx, *, live=None):
    import bus
    from nucleo import dispatch
    from nucleo.workers.session import SessionRecord
    monkeypatch.setattr(dispatch, "about_a_live_errand", lambda *a, **k: "")
    monkeypatch.setattr(dispatch, "_run_session", lambda task: asyncio.sleep(0))
    monkeypatch.setattr(dispatch, "_name_errand", lambda rec: None)

    async def _inject(which, msg):
        return [which]
    monkeypatch.setattr(dispatch, "inject", _inject)

    async def run():
        bus.reset()
        dispatch._SESSIONS.clear()
        if live:
            dispatch._SESSIONS[live[0]] = SessionRecord(task_id=live[0], kind="web", status="running", goal=live[1])
        stop = asyncio.Event()
        task = asyncio.create_task(dispatch.run_listener(stop))
        await asyncio.sleep(0.05)
        errand.escalate_to_slowbrain(request, context=ctx)
        await asyncio.sleep(0.25)
        stop.set(); await asyncio.sleep(0.05); task.cancel()
    asyncio.run(run())
    recs = dict(dispatch._SESSIONS)
    dispatch._SESSIONS.clear()
    return recs


def test_a_row_nobody_adopted_is_forgotten_and_an_adopted_one_is_not(db):
    old = ledger.born(90, "find me a flat in Madrid", {})
    ts.task_patch(old, started_at=1, created_at=1)
    keep = ledger.born(91, "a used acoustic guitar", {})
    ts.task_patch(keep, state="running", visible=True, started_at=1, created_at=1)
    ledger.reconciled({keep})
    ids = {r["id"] for r in _rows()}
    assert old not in ids and keep in ids


def test_a_late_birth_never_rewinds_a_row_the_dispatcher_moved_on(db):
    uid = ledger.task_uid(92)
    ts.task_put({"id": uid, "goal": "find me a flat in Madrid", "state": "running", "visible": True, "mode": "now"})
    ledger.born(92, "find me a flat in Madrid", {})
    row = next(r for r in _rows() if r["id"] == uid)
    assert row["state"] == "running" and row["visible"]
