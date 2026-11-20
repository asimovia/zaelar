"""A request joins the open flow it belongs to BEFORE anything is opened (V2-784, 2026-10-21).

The operator's demo pass, 19:23: «…twenty seven inch four k monitors?» launched a listing hunt; he kept talking,
that turn was cancelled, but the hunt ran on in its thread and was nobody's flow yet. «…Under four hundred bucks…
show me when we got them» arrived 8 s later, found nothing open, and launched a second hunt with a second sheet.
The dispatcher's dedup later folded the second WORKER into the first and left the second SHEET open forever.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from nucleo.acts import search_listing
from nucleo.dispatch import fold as flow_of
from nucleo.errands import launches

FRAGMENT = "Okay. Can you find me, like, three twenty seven inch four k monitors?"
WHOLE = ("Okay. Can you find me, like, three twenty seven inch four k monitors? Under four hundred bucks. "
         "Or so, So show me when we got them.")
REQ = {"query": "27 inch 4K monitor"}


@pytest.fixture
def hunts(monkeypatch):
    """`run` replaced by a recorder; the first call blocks like a hunt still on the network."""
    launches.reset()
    calls, gate = [], threading.Event()

    def fake_run(query, **kw):
        calls.append(kw)
        if len(calls) == 1:
            gate.wait(5)
        return {"delivered": False, "n": 0, "sheet": kw.get("sheet") or kw.get("new_sheet"), "escalated": 0,
                "reason": "", "ctx": ""}

    monkeypatch.setattr(search_listing, "fast_pass", fake_run)
    monkeypatch.setattr(search_listing, "FAST_PASS_BUDGET_S", 0.3)
    monkeypatch.setattr(search_listing, "_taken_line", lambda: "")
    monkeypatch.setattr("nucleo.request.append.about_a_live_errand", lambda text, live: "")
    monkeypatch.setattr("nucleo.dispatch.pending_summaries", lambda: [])
    monkeypatch.setattr("nucleo.acts.errand.pending", lambda: [])
    yield calls
    gate.set()
    launches.reset()


def test_the_sentence_that_finishes_a_cancelled_fragment_reuses_its_sheet(hunts):
    async def scene():
        first = asyncio.ensure_future(search_listing.listings({"text": FRAGMENT}, REQ))
        await asyncio.sleep(0.05)
        first.cancel()                               # he kept talking: the fragment's turn is cancelled
        await asyncio.sleep(0.05)
        await search_listing.listings({"text": WHOLE}, REQ)

    asyncio.run(scene())
    assert len(hunts) == 2
    sheet = hunts[0]["new_sheet"]
    assert sheet, "the first hunt had no sheet of its own from the start"
    assert hunts[1]["sheet"] == sheet and not hunts[1]["new_sheet"], \
        "the whole sentence opened a SECOND sheet beside the hunt it finishes"


# ── F3/F4 · the dispatcher's late fold is an alarm, and it no longer leaves a sheet behind ──────────────────



def test_a_late_fold_into_the_same_sheet_closes_nothing(monkeypatch):
    from types import SimpleNamespace

    from voice import observer
    seen = []
    monkeypatch.setattr(observer, "emit", lambda *a, **kw: seen.append((a, kw)))
    monkeypatch.setattr("nucleo.dispatch.get_record", lambda tid: SimpleNamespace(sheet="ls1"))
    monkeypatch.setattr("nucleo.dispatch.sheet_of", lambda rec: rec.sheet)
    assert flow_of.late_fold("7", {"sheet": "ls1"}) == ""
    assert not any(a[:2] == ("widget", "close") for a, _ in seen)
