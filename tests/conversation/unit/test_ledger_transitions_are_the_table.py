"""The ledger's transitions are ONE table, and nothing moves outside it (node 13.10).

For every item kind: every listed transition is taken, every unlisted one (including any move out of a final state)
is refused with `conv_ledger/refused` and writes nothing. A follow-up is its own item, apart from the effect that
sent: the effect can be delivered while its follow-up still waits. The ledger's events are said only when the
transaction commits, and a taken lease writes nothing and says `stale_epoch`. Over both stores.
"""
from __future__ import annotations

import itertools

import pytest

from conversation.ledger import INITIAL, TRANSITIONS, InvalidTransition
from conversation.ports import StaleEpoch
from conversation.types import ItemKind

ALL_STATES = {k: {INITIAL[k]} | set(TRANSITIONS[k]) | {t for tos in TRANSITIONS[k].values() for t in tos}
              for k in ItemKind}


def _reach(kind: ItemKind, target: str) -> list[str]:
    """A path of listed moves from the initial state to `target` (breadth first)."""
    frontier, seen = [[INITIAL[kind]]], {INITIAL[kind]}
    while frontier:
        path = frontier.pop(0)
        if path[-1] == target:
            return path
        for nxt in sorted(TRANSITIONS[kind].get(path[-1], ())):
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(path + [nxt])
    raise AssertionError(f"{kind}: {target} unreachable")


@pytest.mark.parametrize("kind", list(ItemKind))
def test_every_listed_move_is_taken_and_every_other_is_refused(book, telemetry, kind):
    n = itertools.count()
    for frm, to in itertools.product(sorted(ALL_STATES[kind]), sorted(ALL_STATES[kind])):
        item = f"{kind}-{next(n)}"
        with book.tx() as b:
            b.open(kind, item)
            for step in _reach(kind, frm)[1:]:
                b.move(item, step)
        listed = to in TRANSITIONS[kind].get(frm, ())
        before = len(telemetry.events)
        if listed:
            with book.tx() as b:
                assert b.move(item, to)["state"] == to
        else:
            with pytest.raises(InvalidTransition):
                with book.tx() as b:
                    b.move(item, to)
            assert book.snapshot().get("items", item)["state"] == frm
            assert [lab for _k, lab, _p in telemetry.events[before:]] == ["refused"]


def test_a_followup_is_its_own_item_apart_from_the_effect(book):
    with book.tx() as b:
        b.open(ItemKind.EFFECT, "x1", data={"tool": "send_message"})
        b.open(ItemKind.FOLLOWUP, "f1", data={"effect": "x1", "scope": "thread:th1"}, waiting_on="reply")
        for s in ("submitted", "provider_accepted", "delivered"):
            b.move("x1", s)
    snap = book.snapshot()
    assert snap.get("items", "x1")["state"] == "delivered" and snap.get("items", "f1")["state"] == "waiting"
    with book.tx() as b:
        b.move("f1", "matched")
    with pytest.raises(InvalidTransition):
        with book.tx() as b:
            b.move("x1", "submitted")                      # a delivered effect never goes back to sending


def test_events_are_said_only_when_the_transaction_commits(book, telemetry):
    with pytest.raises(RuntimeError):
        with book.tx() as b:
            b.open(ItemKind.REQUEST, "r1")
            raise RuntimeError("boom")
    assert telemetry.labels("conv_ledger") == [] and book.snapshot().get("items", "r1") is None
    with book.tx() as b:
        b.open(ItemKind.REQUEST, "r1", data={"req": "r1"})
        b.attach("r1", "e_1", decided_by="id")
    assert telemetry.labels("conv_ledger") == ["conv_ledger/opened", "conv_ledger/attached"]


def test_a_taken_lease_writes_nothing_and_says_so(book, store, telemetry):
    store.acquire("acct-test", "another-process")
    with pytest.raises(StaleEpoch):
        with book.tx() as b:
            b.open(ItemKind.REQUEST, "r9")
    assert book.snapshot().get("items", "r9") is None
    assert telemetry.labels("conv_ledger") == ["conv_ledger/stale_epoch"]


def test_open_is_idempotent_by_id(book):
    with book.tx() as b:
        first = b.open(ItemKind.TASK, "t1", owner="worker:t1")
        again = b.open(ItemKind.TASK, "t1", owner="conversation")
    assert again == first and again["owner"] == "worker:t1"


#: §6.4 of the plan, written here independently of the code: the table may not drift from it.
SPEC = {
    ItemKind.REQUEST: {"open": {"answered", "handed_off", "silent", "recovered", "failed"}},
    ItemKind.TASK: {"started": {"running", "waiting", "failed", "cancelled"},
                    "running": {"waiting", "done", "failed", "cancelled"},
                    "waiting": {"running", "done", "failed", "cancelled"}},
    ItemKind.QUESTION: {"asked": {"presented", "expired", "superseded"},
                        "presented": {"answered", "expired", "superseded"}},
    ItemKind.GRANT: {"active": {"spent", "expired", "revoked"}},
    ItemKind.HANDLE: {"issued": {"presented", "expired"}, "presented": {"spent", "expired"}},
    ItemKind.DELEGATION: {"active": {"exhausted", "expired", "revoked"}},
    ItemKind.EFFECT: {"claimed": {"submitted", "rejected", "submission_unknown"},
                      "submitted": {"provider_accepted", "rejected", "submission_unknown"},
                      "submission_unknown": {"provider_accepted", "rejected"},
                      "provider_accepted": {"delivered", "delivery_unconfirmed", "failed"}},
    ItemKind.FOLLOWUP: {"waiting": {"matched", "expired"}},
    ItemKind.TO_TELL: {"pending": {"told", "coalesced", "expired", "deferred"},
                       "deferred": {"pending", "told", "coalesced", "expired"}},
}


def test_the_table_is_the_specified_one_and_spent_or_ended_never_comes_back():
    assert {k: {f: set(t) for f, t in v.items()} for k, v in TRANSITIONS.items()} == SPEC
    for kind in ("handle", "grant", "delegation"):
        for end in ("spent", "expired", "revoked", "exhausted"):
            assert end not in TRANSITIONS[ItemKind(kind)], f"{kind}: {end} must be final"
