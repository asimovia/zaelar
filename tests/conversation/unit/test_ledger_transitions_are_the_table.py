"""The ledger keeps two items and their transitions are ONE table; nothing moves outside it (node 13.10).

A request and the reservation of an effect — nothing else: tasks, questions, what is owed and mandates are the host's
rows, referred to by id. For both kinds: every listed transition is taken, every unlisted one (including any move out
of a final state) is refused with `conv_ledger/refused` and writes nothing. An accepted effect is final here: whether
it was delivered is the connector's receipt. The ledger's events are said only when the transaction commits, and a
taken lease writes nothing and says `stale_epoch`. Over both stores.
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


def test_two_kinds_and_an_accepted_effect_never_goes_back_to_sending(book):
    assert [str(k) for k in ItemKind] == ["request", "effect"]
    with book.tx() as b:
        b.open(ItemKind.EFFECT, "x1", data={"tool": "w_tool"})
        for s in ("submitting", "provider_accepted"):
            b.move("x1", s)
    with pytest.raises(InvalidTransition):
        with book.tx() as b:
            b.move("x1", "submitting")


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
        first = b.open(ItemKind.REQUEST, "r1", owner="worker:t1")
        again = b.open(ItemKind.REQUEST, "r1", owner="conversation")
    assert again == first and again["owner"] == "worker:t1"


#: the two items as the design writes them, independently of the code: the table may not drift from it.
SPEC = {
    ItemKind.REQUEST: {"open": {"answered", "handed_off", "silent", "recovered", "failed"}},
    ItemKind.EFFECT: {"claimed": {"submitting", "withdrawn"},
                      "submitting": {"provider_accepted", "rejected", "submission_unknown"},
                      "submission_unknown": {"provider_accepted", "rejected"}},
}


def test_the_table_is_the_specified_one_and_an_end_never_comes_back():
    assert {k: {f: set(t) for f, t in v.items()} for k, v in TRANSITIONS.items()} == SPEC
    for end in ("answered", "silent", "recovered", "failed", "withdrawn", "provider_accepted", "rejected"):
        assert all(end not in TRANSITIONS[k] for k in ItemKind), f"{end} must be final"
