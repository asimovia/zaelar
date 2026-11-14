"""A canvas order is pending until its screen answers (V2-907 T3, `widgets/screen_orders.py`).

Emitting an order says nothing about the screen. The ledger gives it a `seq`; its target screens answer through
their report; only then is it `confirmed` (one did it), `noop:<why>` (none had anything to do) or `refused`. A screen
that never answers within `PENDING_S` (V2-884's ack clock, shared) leaves it `unconfirmed`; nobody to answer is
`unconfirmed` too; two targets need two answers; a non-target cannot answer for a target.

Disarm: `issue` records the order as already answered by every target (resolve at issue) → red.
"""
from __future__ import annotations

import importlib
import pathlib
import shutil
import threading
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[4]
PHONE, DESK = "mobile:p-ava", "desktop:d-ava"


@pytest.fixture
def so():
    from widgets import screen_orders
    screen_orders._reset_for_tests()
    yield screen_orders
    screen_orders._reset_for_tests()


def test_the_window_is_v2_884s_clock(so):
    from widgets import state_render
    assert so.PENDING_S == state_render.PENDING_S
    assert "from widgets.state_render import PENDING_S" in (ROOT / "widgets" / "screen_orders.py").read_text()


def test_an_ack_confirms(so):
    seq = so.issue("show", "agenda", [DESK])
    assert so.outcome(seq) == "pending" and [p["seq"] for p in so.pending(DESK)] == [seq]
    assert so.ack(DESK, [{"seq": seq, "ok": True, "why": "done"}]) == 1
    assert so.outcome(seq) == "confirmed" and so.pending(DESK) == []
    assert so.ack(DESK, [{"seq": seq, "ok": False, "why": "refused"}]) == 0     # a repeat changes nothing
    assert so.outcome(seq) == "confirmed"


def test_not_open_is_a_noop(so):
    seq = so.issue("close", "agenda", [PHONE])
    so.ack(PHONE, [{"seq": seq, "ok": True, "why": "not_open"}])
    assert so.outcome(seq) == "noop:not_open"
    r = so.issue("show", "musica", [PHONE])
    so.ack(PHONE, [{"seq": r, "ok": False, "why": "refused"}])
    assert so.outcome(r) == "refused"


def test_no_ack_in_the_window_is_unconfirmed(so, monkeypatch):
    seq = so.issue("close", "agenda", [DESK])
    assert so.outcome(seq) == "pending"
    later = time.time() + so.PENDING_S + 0.1
    monkeypatch.setattr(so.time, "time", lambda: later)
    assert so.outcome(seq) == "unconfirmed" and so.pending(DESK) == []
    assert so.outcome(so.issue("close_all", "", [])) == "unconfirmed"     # nobody to answer
    assert so.outcome(10_000) == "unknown"


def test_two_targets_need_two_acks(so):
    seq = so.issue("close", "agenda", [DESK, PHONE])
    so.ack(DESK, [{"seq": seq, "ok": True, "why": "done"}])
    assert so.outcome(seq) == "pending"
    assert so.ack("desktop:stranger", [{"seq": seq, "ok": True, "why": "done"}]) == 0   # not a target
    assert so.outcome(seq) == "pending"
    so.ack(PHONE, [{"seq": seq, "ok": True, "why": "already_closed"}])
    assert so.outcome(seq) == "confirmed"
    both = so.issue("close", "musica", [DESK, PHONE])
    so.ack(DESK, [{"seq": both, "ok": True, "why": "not_open"}])
    so.ack(PHONE, [{"seq": both, "ok": True, "why": "not_open"}])
    assert so.outcome(both) == "noop:not_open"


def test_a_waiting_reader_wakes_on_the_answer(so):
    seq = so.issue("show", "agenda", [DESK])
    threading.Timer(0.05, lambda: so.ack(DESK, [{"seq": seq, "ok": True, "why": "done"}])).start()
    t0 = time.time()
    assert so.outcome(seq, wait_s=2.0) == "confirmed" and time.time() - t0 < 1.5


def test_seq_only_goes_forward(so):
    a, b = so.issue("show", "a", [DESK]), so.issue("show", "b", [DESK])
    assert b > a


def test_disarmed_resolve_at_issue_turns_red(so):
    """Disarm: every target is recorded as having answered `done` at issue — the pending tests must fail."""
    src = ROOT / "widgets" / "screen_orders.py"
    orig = src.read_text(encoding="utf-8")
    old = '"acks": {}}'
    assert old in orig, "the disarm no longer matches screen_orders.py"
    try:
        src.write_text(orig.replace(old, '"acks": {d: "done" for d in devs}}'), encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        assert old not in src.read_text(encoding="utf-8")
        importlib.reload(so)
        with pytest.raises(AssertionError):
            test_an_ack_confirms(so)
        so._reset_for_tests()
        with pytest.raises(AssertionError):
            test_two_targets_need_two_acks(so)
    finally:
        src.write_text(orig, encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        importlib.reload(so)
