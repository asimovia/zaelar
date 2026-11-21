"""A send is seen step by step in the flow of the order that opened it (C2 P3, pin 8).

The operator's decision P-3: the send is seen WHOLE, like a worker's playbook. Its steps are declared data
(`nucleo/send/steps.json`), each done when a field of its draft holds; every step the owner emits runs in the trace of
the order that opened the draft — a later turn of his the owner takes is folded into that flow, and the receipt's
steps land there too — and moves a `task` card shaped like a worker's (`start`, `plan` once, `progress`, `end`), with
`runner: send`.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.send import draft, owner, receipt, steps
from voice import trace


@pytest.fixture
def seen(monkeypatch):
    from nucleo.send import card
    from voice import observer
    got = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, **kw: got.append((kind, label, trace.current(),
                                                                                kw.get("extra") or {})))
    monkeypatch.setattr(card, "paint", lambda d: None)
    draft.reset()
    yield got
    draft.reset()


def _done(d) -> dict:
    return {s["id"]: ("skipped" if s["skipped"] else s["done"]) for s in steps.plan(d)}


def test_the_steps_are_read_off_the_drafts_own_fields():
    d = draft.Draft(said="w_tell ana goodnight")
    assert _done(d) == {"opened": True, "who": False, "text": False, "reach": False, "confirm": False,
                        "go_ahead": False, "receipt": False}
    d.target, d.text, d.heard = {"name": "W_Ana", "platform": "w_chat"}, "w_goodnight", True
    assert [k for k, v in _done(d).items() if v is True] == ["opened", "who", "text", "reach", "confirm"]
    d.heard, d.ref, d.state = False, "r1", draft.SENT                   # sent by the card's own Send: never asked aloud
    assert _done(d)["confirm"] == "skipped" and _done(d)["go_ahead"] is True and _done(d)["receipt"] is True


def test_every_step_is_in_the_orders_flow_and_moves_one_send_card(seen, monkeypatch):
    with trace.scope("T_order"):
        d = draft.start("w_tell ana goodnight")
    d.target, d.text = {"name": "W_Ana", "platform": "w_chat"}, "w_goodnight"
    with trace.scope("T_later"):                                       # a step emitted from another turn
        owner._emit("opened", d)
        owner._emit("asked", d)
    from nucleo.request import send_receipt
    d.ref = "r1"
    monkeypatch.setattr(send_receipt, "receipt", lambda w, ref, _x: ("sent", ""))
    monkeypatch.setattr(receipt, "_say", lambda *a, **k: asyncio.sleep(0))
    asyncio.run(receipt.follow(d, poll_s=0))
    assert {t for k, _l, t, _e in seen if k in ("send", "task")} == {"T_order"}
    tasks = [(label, e) for k, label, _t, e in seen if k == "task"]
    assert [lab for lab, _e in tasks] == ["start", "plan", "progress", "progress", "progress", "end"]
    assert all(e["runner"] == "send" and e["id"] == f"send:{d.id}" and e["trace"] == "T_order" for _l, e in tasks)
    assert tasks[-1][1]["ok"] is True and tasks[-1][1]["total"] == len(steps.plan(d))


def test_a_later_turn_the_owner_takes_is_folded_into_the_order(monkeypatch):
    from nucleo.conversation_host import routing, turns
    merged = []
    monkeypatch.setattr(turns, "_merge", lambda into, tid: merged.append((into, tid)))
    d = draft.Draft(said="w_tell ana goodnight", trace="T_order")
    monkeypatch.setattr(draft, "current", lambda: d)

    async def take(text, **kw):
        return True, "w_sent"
    monkeypatch.setattr(owner, "take", take)
    monkeypatch.setattr(turns, "current", lambda: "T_yes")
    assert asyncio.run(routing.HostRoute().take("acct", "w_yes")) == "w_sent"
    assert merged == [("T_order", "T_yes")]


def test_a_draft_that_ends_unsent_ends_its_card(seen):
    with trace.scope("T_order"):
        d = draft.start("w_tell ana goodnight")
    owner._emit("opened", d)
    draft.close(d, draft.CANCELLED)
    ends = [e for k, label, _t, e in seen if k == "task" and label == "end"]
    assert len(ends) == 1 and ends[0]["ok"] is False
