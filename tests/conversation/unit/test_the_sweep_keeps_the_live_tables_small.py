"""The sweep's cost follows what is in course, not the account's history (node 13.28) — and an idle conversation opens
no transaction at all.

The clock's turn runs every 100 ms; what it reads is what is in course — a held text, a dequeued control, a line not
ended, an open request, an open voice — by `scan(table, states)`, never a whole table. Nothing is moved or archived
to keep a table small: what is done stays where it is (the host's hygiene deletes it by age), so a late re-delivery of
an old envelope is still a duplicate. Measured as the rows the sweep's reads return, over both stores.
"""
from __future__ import annotations

from contextlib import contextmanager

from conversation import envelopes as E
from tests.conversation.unit.convkit import ACCT, Harness


class _Counting:
    """The store, with every row a transaction's scan returns counted."""

    def __init__(self, store) -> None:
        self._s, self.rows, self.whole = store, 0, 0

    def __getattr__(self, name):
        return getattr(self._s, name)

    @contextmanager
    def tx(self, lease):
        with self._s.tx(lease) as tx:
            outer = self

            class _Tx:
                def __getattr__(self, name):
                    return getattr(tx, name)

                def scan(self, table, states=None):
                    got = tx.scan(table, states)
                    outer.rows += len(got)
                    outer.whole += states is None
                    return got

            yield _Tx()

    def view(self, account):
        """A run's and an idle sweep's reads go through the view, outside any transaction: counted the same way."""
        v, outer = self._s.view(account), self

        class _View:
            def __getattr__(self, name):
                return getattr(v, name)

            def scan(self, table, states=None):
                got = v.scan(table, states)
                outer.rows += len(got)
                outer.whole += states is None
                return got

            def recent(self, table, n):
                got = v.recent(table, n)
                outer.rows += len(got)
                return got

        return _View()


def _sweep_reads(h: Harness, counting: _Counting) -> tuple[int, int]:
    counting.rows = counting.whole = 0
    h.conv.sweep(h.clock.now_ms())
    return counting.rows, counting.whole


def test_sixty_exchanges_later_the_sweep_reads_only_what_is_in_course(store):
    counting = _Counting(store)
    h = Harness(counting)
    for i in range(60):
        h.at(i * 30_000).utter([([f"w{i}"], 0)])
    h.at(h.clock.mono + 61_000).pump()
    assert [lab for lab, _ in h.closes()].count("answered") == 60
    assert _sweep_reads(h, counting) == (0, 0)                          # sixty done exchanges: nothing to read
    snap = store.snapshot(ACCT)
    assert len(snap.scan("inbox")) >= 60 and not snap.scan("inbox.done")   # nothing was moved anywhere
    first = next(r for _k, r in snap.scan("inbox") if r["kind"] == "user.utterance")
    again = h.conv.inbox.accept(E.from_json({**first["env"], "id": "", "accepted_ms": 0}), h.clock.now_ms())
    assert again.disposition == "duplicate"                              # an old envelope is still a duplicate


def test_what_is_in_course_is_what_the_sweep_reads(store):
    counting = _Counting(store)
    h = Harness(counting)
    for i in range(20):
        h.at(i * 30_000).utter([([f"w{i}"], 0)])
        h.settle(6000)                                                   # each one answered before the next
    t = h.clock.mono + 10
    ws = h.words(["w1"], t)
    from conversation.ear import signals as S
    h.hear(S.VadEdge("d1", "rise", t), S.WordSpan("d1", 99, 1, False, ws, (t, ws[-1][2])), h.beats(t, t + 300))
    h.typed("w9", t + 100)                                               # held behind the open voice
    rows, whole = _sweep_reads(h, counting)
    assert whole == 0 and 1 <= rows <= 5, rows      # the held text (read by the hold and by the liveness, which counts
                                                    # from his last entry in course), its request, the open voice


def test_an_idle_conversation_opens_no_transaction(store):
    """Its timer sweeps and pumps every 250 ms: with nothing in course each look is a read, and no write transaction —
    which would take the shared write lock every other writer of `zaelar.db` waits on — is ever opened."""
    counting = _Counting(store)
    h = Harness(counting)

    class _Record:
        def pair(self, account, said, answered, *, ref):
            return None

    h.conv.record = _Record()
    h.typed("w1", 100)
    h.at(10_000).pump()
    opened = []
    real = counting._s.tx

    def tx(lease):
        opened.append(1)
        return real(lease)

    counting._s.tx = tx
    for i in range(40):
        h.conv.sweep(11_000 + i * 250)
        h.at(11_000 + i * 250).pump()
    assert not opened, f"{len(opened)} transactions while idle"
