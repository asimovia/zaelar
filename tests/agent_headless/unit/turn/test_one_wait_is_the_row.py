"""One wait: the ROW (V2-878 §4) — nodes 2.1680, 2.1681, 2.1682.

Three stores used to hold a question waiting on him: the widget gate's memory (`widgets/confirm._PENDING`, 90 s), the
task gate's (`dispatch/confirm._PENDING_CONFIRM`, 300 s) and the durable rows (`waiting_for=user_answer`). With two
waiting, a bare «yes» answered «the most recent»; a longer one was handed to a second model on the hot path; a
suspension's frozen hours expired every in-memory question at once on wake; a scheduled notice that asked something
was no question at all once it had been said.

The mechanism, each class with its test:

  1. Every gate question waits on a ROW through the one asker, with its `ask_id` and two declared answers; the memory
     registries are this process's index of those rows. Which question a reply answers is the brief's binding pick
     over the rows (`worker_api_bind`), never `max(ts)` — and no model is asked anything to decide it (2.1680).
  2. Nothing on a row expires by the wall clock: an offer parked ten minutes of a frozen clock still waits, and after a
     restart its row alone answers (2.1681).
  3. A scheduled notice that asks waits on a row too, so the brief's binding sees it and his answer ends it (2.1682).

Disarms (seen red): `pending_confirm`/`resolve` back to «the last one asked» (`max(ts)`) → 2.1680 red; an offer with no row
(`asker.open_row` → "") → 2.1681 red; `notice_ask.asks` → False → 2.1682 red.
"""
from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace

import pytest

from nucleo.circuit import asker
from nucleo.cli import worker_api  # noqa: F401 — the package first: its answer module imports it back
from nucleo.dispatch import confirm as dc
from widgets import confirm as wc


@pytest.fixture
def no_model(monkeypatch):
    """Zero model calls: any reach for the fast model on this path fails the test."""
    from nucleo.llm import fast_client

    async def _never(*a, **k):
        raise AssertionError("a model was asked which question his reply answers")
    monkeypatch.setattr(fast_client.FastClient, "complete", _never)


@pytest.fixture
def clean(monkeypatch):
    from nucleo.request import inline_ask
    wc.reset()
    dc._PENDING_CONFIRM.clear()
    dc._EXPIRED_CONFIRM.clear()
    inline_ask._TAKEN.clear()
    launched: list = []
    monkeypatch.setattr("nucleo.acts.errand.escalate_to_slowbrain",
                        lambda req, context=None: launched.append((req, context)) or 1)
    yield launched
    wc.reset()
    dc._PENDING_CONFIRM.clear()


def _open(ask_id_of: str) -> dict:
    return next(a for a in worker_api.open_asks() if a["ask_id"] == ask_id_of)


# ── 2.1680 · two open questions and a «yes» → the one the brief names, zero model calls ──────────────────────────



# ── 2.1681 · a parked offer survives ten minutes of a frozen clock and a restart ─────────────────────────────────

def test_a_parked_offer_survives_a_suspension_and_a_restart(clean, monkeypatch):
    dc.remember_offer("busca vuelos a Roma para el puente", context={"kind": "web"}, question="¿Te busco vuelos?")
    wc.request("delete", "meteo", "¿Borro la app del tiempo?", notify_ui=False)
    (key, offer), = dc._PENDING_CONFIRM.items()
    assert offer.get("ask_id"), "the offer is not on a row"

    woke = time.time() + 600                                     # the process was frozen ten minutes, then woke
    monkeypatch.setattr(time, "time", lambda: woke)
    assert dc.pending_confirm(key), "the wall clock expired a question that waits on its row"
    assert "CADUCÓ" not in dc.confirm_line() and "OFRECISTE" in dc.confirm_line()
    assert "meteo" in wc.pending() and not wc.drain_expired_notices()

    dc._PENDING_CONFIRM.clear()                                  # a restart: this process's memory is gone
    wc._PENDING.clear()
    a = _open(offer["ask_id"])
    assert a["candidates"] and len(a["candidates"]) == 2, "the row lost its declared answers"
    assert asyncio.run(worker_api.answer(a["ask_id"], a["candidates"][0], choice=0))
    (req, ctx), = clean
    assert req == "busca vuelos a Roma para el puente" and ctx["confirmed"] is True


# ── 2.1682 · a scheduled notice that asks is a waiting row the brief's binding sees ─────────────────────────────

@pytest.fixture
def quiet_notice(monkeypatch):
    from nucleo.pulse import notices
    from voice import proactive

    async def _say(*a, **k):
        return True
    monkeypatch.setattr(proactive, "notify", _say)
    monkeypatch.setattr(notices, "push", lambda row: 0)
    return notices


@pytest.mark.parametrize("q", ["¿Te has tomado la pastilla de la tarde?", "Did you take the evening pill?",
                               "午後の薬は飲みましたか？"])
def test_a_scheduled_notice_that_asks_waits_on_a_row(clean, quiet_notice, q):
    res = asyncio.run(quiet_notice.notify("aviso", q, key=f"job:7:{abs(hash(q))}", kind="reminder"))
    ask_id = str((quiet_notice.get(res["id"])["detail"] or {}).get("ask_id") or "")
    assert ask_id, "a notice that asks opened no question"
    a = _open(ask_id)
    assert a["question"] == q
    from nucleo.switchboard import board
    assert any(p["ask_id"] == ask_id and p["state"] == "waiting" for p in board.open_processes()), \
        "the switchboard's board does not see the notice's question"
    assert asyncio.run(quiet_notice.notify("aviso", q, key=f"job:7:{abs(hash(q))}", kind="reminder"))["duplicate"]
    assert sum(x["question"] == q for x in worker_api.open_asks()) == 1, "the same firing opened a second question"

    assert asyncio.run(worker_api.answer(ask_id, "sí"))       # his answer, bound to it, ends the row
    assert not any(x["ask_id"] == ask_id for x in worker_api.open_asks())


def test_a_notice_that_only_tells_opens_no_question(clean, quiet_notice):
    before = len(worker_api.open_asks())
    asyncio.run(quiet_notice.notify("aviso", "Cita con el dentista a las 10.", key="job:8:1", kind="reminder"))
    asyncio.run(quiet_notice.notify("zaelar", "Done — did it land?", key="info:1", kind="info"))
    assert len(worker_api.open_asks()) == before


def test_a_no_through_the_task_gate_ends_the_row_it_waited_on(clean):
    """His «no» read by the in-memory gate ends the parked errand's row too — it left it waiting until its deadline."""
    task = SimpleNamespace(kind="generic", trusted=True, context={})
    dc.remember_confirm("k9", "paga la factura del gas", task)
    ask_id = dc.make_durable("k9", SimpleNamespace(uid=asker.open_row("paga la factura del gas", kind="generic")))
    assert any(a["ask_id"] == ask_id for a in worker_api.open_asks())
    assert dc.resolve_confirm(False, "k9")["ok"] is False
    assert not any(a["ask_id"] == ask_id for a in worker_api.open_asks()), "the row still waits on a «no»"
    assert not clean
