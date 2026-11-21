"""A status with no milestone says the facts that moved, never one fixed line (three-tasks-at-once EN, 2026-10-15).

«under way, nothing new yet» was said for the game and the monitor turn after turn while both were working. With
no milestone to say, the line now carries its plan step, or how long it has been running — both from the live
record (`pending_summaries`), both different on the next ask.
"""
import pytest


@pytest.fixture
def en(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")


def test_the_live_record_carries_those_facts(monkeypatch):
    from nucleo import dispatch
    from nucleo.errands import named as named_errand
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [{"id": "t1", "request": "find a monitor", "secs": 200,
                                                                  "done": 1, "total": 4}])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: None)
    e = next(x for x in named_errand.known() if x["id"] == "t1")
    assert (e["secs"], e["done"], e["total"]) == (200, 1, 4)
