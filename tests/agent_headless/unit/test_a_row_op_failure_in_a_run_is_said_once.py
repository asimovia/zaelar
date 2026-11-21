"""A card op that fails on a row it CLAIMED inside a run is said once — by the run (INI-078 L1, B6).

The conversation manager runs a card's act through `data_ops.dispatch_and_report` and says a refusal from the act's
receipt. When the same act names a candidate of a row waiting on his answer, `inline_ask.claim` hands the op that row.
`_late` read ANY row as «no turn of his is left to say it», so the refusal also went out of turn through `notices`:
two lines for one failure. Late is now a row the CALLER hands (a resume out of turn), or an answer past the mouth's wait.

Disarm: `_late = … or bool(row)` again — the claimed case reports late and this goes red.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.acts import data_ops

REFUSAL = {"ok": False, "error": "selector_missing", "message": "I could not tell which one, so nothing changed."}


@pytest.fixture
def scene(monkeypatch):
    import widgets
    from nucleo.request import inline_ask
    late: list = []

    async def _dispatch(_tag, _body):
        return dict(REFUSAL)

    async def _report(wid, action, res, *, late=False, row=""):
        late_seen.append((late, row))
        return False

    late_seen = late
    monkeypatch.setattr(widgets, "dispatch_tag", _dispatch)
    monkeypatch.setattr(inline_ask, "claim", lambda w, a, p: ("row-claimed", False))
    monkeypatch.setattr(inline_ask, "reached", lambda *a, **k: None)
    monkeypatch.setattr(inline_ask, "held", lambda *a, **k: False)
    monkeypatch.setattr(data_ops, "_write_ending", lambda *a, **k: None)
    monkeypatch.setattr(data_ops, "report_failure", _report)
    return late


def test_a_row_the_op_claimed_in_a_run_is_not_late(scene):
    asyncio.run(data_ops.dispatch_and_report("agenda", "cancel_meeting", {"title": "dentist"}))
    assert scene == [(False, "row-claimed")], "the run says this refusal: nothing goes out of turn too"


def test_a_row_the_caller_resumes_is_late(scene):
    asyncio.run(data_ops.dispatch_and_report("agenda", "cancel_meeting", {"title": "dentist"}, row="row-handed"))
    assert scene == [(True, "row-handed")], "a resume out of turn has no run to say it: notices does"
