"""The sweep's cost follows what is in course, not the account's history (node 13.28; review 2, NM2).

What is done — an accounted envelope, an ended line, a final request or effect, a sealed or final intervention — moves
out of the live tables once older than `retain_ms`; the newest turns always stay. Archived is not forgotten: a late
re-delivery of an archived envelope is still a duplicate, and nothing that is open is ever moved.
"""
from __future__ import annotations

from conversation import envelopes as E
from conversation.config import Config
from tests.conversation.unit.convkit import ACCT, Harness

LIVE = ("inbox", "items", "says", "interventions")


def _count(store, table: str) -> int:
    return len(store.snapshot(ACCT).scan(table))


def test_sixty_exchanges_over_half_an_hour_leave_only_the_last_minutes_live(store):
    h = Harness(store, config=Config(retain_ms=5 * 60_000, prune_every_ms=60_000))
    for i in range(60):
        h.at(i * 30_000).utter([([f"w{i}"], 0)])
    h.at(h.clock.mono + 61_000).pump()
    live = {t: _count(store, t) for t in LIVE}
    done = {t: _count(store, f"{t}.done") for t in LIVE}
    assert all(n <= 15 * 4 for n in live.values()), live                # ~the last five minutes, not sixty exchanges
    assert done["inbox"] >= 40 and done["items"] >= 40, done
    assert [lab for lab, _ in h.closes()].count("answered") == 60
    first = store.snapshot(ACCT).get("inbox.done", "e_000003") or next(
        r for _k, r in store.snapshot(ACCT).scan("inbox.done") if r["kind"] == "user.utterance")
    again = h.conv.inbox.accept(E.from_json({**first["env"], "id": "", "accepted_ms": 0}), h.clock.now_ms())
    assert again.disposition == "duplicate"                              # archived, still a duplicate
    assert len(store.snapshot(ACCT).scan("turns")) <= 4 * Config().conversation_turns


def test_nothing_in_course_is_ever_archived(store):
    h = Harness(store, config=Config(retain_ms=1000, prune_every_ms=0))
    with h.conv.book.tx() as b:
        from conversation.types import ItemKind
        b.open(ItemKind.EFFECT, "x1", data={"tool": "w_tool"})
        b.move("x1", "submitting")
    h.at(10 ** 7).pump()
    assert h.conv.prune(h.clock.now_ms()) == 0 and store.snapshot(ACCT).get("items", "x1")["state"] == "submitting"
