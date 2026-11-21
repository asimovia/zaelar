"""Node 3.69 — a decision is attributable, and the timeline says whether anybody USED it.

V2-726 A6a. The audit asked the only question that decides whether any of this is worth its round
trip — «which verdict changed which outcome?» — and the engine could not answer it:

  · the brief's event reported `max()` confidence across its questions, so one sure canvas verb hid
    three unsure ones behind a 0.99 and no consumer's own threshold could be checked;
  · `jev.read` already computed `info["used"]` and EVERY consumer threw it away, so the record said
    Jev was ASKED and never whether the answer moved anything;
  · no handle carried an id, so two events in a real session could only be attributed to the same
    turn by their timestamps — temporal, not a join, which is not evidence;
  · `select_many` returned `[]` for «nothing fits», «no key», «network down» and «switched off»,
    which are two answers and two absences, and they call for opposite behaviour.

What this file pins is that each of those now produces a DISTINCT, bounded record. It does not
claim the verdicts are good — that is A6b's report, against adjudicated cases.
"""
from __future__ import annotations


import pytest

from nucleo import jev


@pytest.fixture
def events(monkeypatch):
    """Capture the timeline instead of writing it. A test never touches the operator's real log —
    and this one would write into it twice per read (V2-726 §7.3 rule 2, paid for once already)."""
    seen: list[dict] = []
    monkeypatch.setattr("voice.observer.emit",
                        lambda kind, label, text="", role="", extra=None:
                        seen.append({"kind": kind, "label": label, "text": text,
                                     "extra": dict(extra or {})}))
    jev.reset_read_events()
    return seen


@pytest.fixture
def wire(monkeypatch):
    monkeypatch.setattr(jev, "_read_key", lambda: "k-for-tests")
    monkeypatch.delenv("ZAELAR_JEV", raising=False)
    jev.reset_breaker()

    class _Wire:
        def __init__(self) -> None:
            self.calls: list[dict] = []
            self.answers: dict[str, tuple[str, float]] = {}

        def __call__(self, state, questions, timeout_s):
            self.calls.append({"state": state, "questions": questions})
            return {"answers": {k: {"choice": (a := self.answers.get(k, (next(iter(q["criteria"])), 0.95)))[0],
                                    "confidence": a[1], "probabilities": {a[0]: a[1]}}
                                for k, q in questions.items()}}

    w = _Wire()
    monkeypatch.setattr(jev, "_post_many", w)
    return w


def _settle(handle, t=2.0):
    if handle and handle.get("event"):
        handle["event"].wait(t)
    return handle


# ── selection: an empty answer is not an absent one ──────────────────────────────────────────────
def test_switched_off_is_its_own_status(wire, monkeypatch):
    monkeypatch.setenv("ZAELAR_JEV", "0")
    picked, status = jev.select_many_status([{"id": "t1"}], "¿es este?", key=lambda r: r["id"])
    assert (picked, status) == ([], jev.DISABLED)


def test_a_single_candidate_still_costs_nothing(wire, monkeypatch):
    """Unchanged by A6a, and worth pinning beside it: one candidate is taken without asking. Paying
    800 ms to confirm what nothing contradicts is the call V2-726 exists to stop making."""
    from nucleo.errands import task_recall as tr
    monkeypatch.setattr(tr, "candidates", lambda q, limit=5: [{"id": "t1", "title": "x"}])
    out = tr.resolve("lo del piso")
    assert out["ok"] is True and out["how"] == "único"
    assert wire.calls == []
