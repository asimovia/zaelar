"""A verdict that cannot be READ is never «no verdict» in silence (V2-903 P2-7).

`verdicts.read` is the one reader of the brief's verdicts. Any exception inside it returned `(fallback, None)` — «no
verdict» — and every veto that verdict held lifted without a trace: a model call a sure verdict would have refused ran,
and nothing on the timeline or the status panel said why. Now the fall-through is the same (the turn never breaks on a
classifier), but it is LOUD: an `is_error` event naming the key and the engine row of the health panel turns red.
Disarm: drop the `_unreadable` call from the `except` — both assertions go red.
"""
from __future__ import annotations

import pytest

from nucleo.turn import verdicts


@pytest.fixture
def broken_jev(monkeypatch):
    from nucleo import jev
    from voice import health_state, observer

    def _boom(*_a, **_k):
        raise KeyError("result")
    monkeypatch.setattr(jev, "read", _boom)
    events = []
    monkeypatch.setattr(observer, "emit", lambda kind, label="", **kw: events.append((label, kw)))
    health_state.clear("engine")
    verdicts._SAID.clear()
    yield events
    health_state.clear("engine")


@pytest.mark.parametrize("key", ["screen_action", "stop_errand", "message_channel"])
def test_a_failed_read_is_said_and_marked(broken_jev, key):
    from voice import health_state
    choice, info = verdicts.read({"turn_id": "t-7"}, key, "fallback")
    assert (choice, info) == ("fallback", None), "the turn must still run on a broken classifier"
    errs = [kw for label, kw in broken_jev if "unreadable" in label]
    assert errs and errs[0]["extra"]["key"] == key and errs[0]["extra"]["is_error"], broken_jev
    mark = health_state.get("engine")
    assert mark and key in mark["text"] and "KeyError" in mark["text"], mark


def test_the_veto_reader_still_lets_the_call_run_but_not_silently(broken_jev):
    assert verdicts.against_the_model({"turn_id": "t-8"}, "screen_action", lambda c: False) == verdicts.RUN
    assert any("unreadable" in label for label, _kw in broken_jev)


def test_a_readable_verdict_marks_nothing(monkeypatch):
    from nucleo import jev
    from voice import health_state
    health_state.clear("engine")
    monkeypatch.setattr(jev, "read", lambda h, k, f, min_confidence=0.5: ("keep", {"confidence": 0.9}))
    assert verdicts.read({"turn_id": "t-9"}, "stop_errand", None)[0] == "keep"
    assert health_state.get("engine") is None


def test_the_same_failure_is_said_once_a_minute_not_per_read(broken_jev):
    """Audit P2-7: a classifier that breaks breaks on every read of the turn — one event per (key, type) a minute."""
    for _ in range(5):
        verdicts.read({"turn_id": "t-10"}, "screen_action", None)
    verdicts.read({"turn_id": "t-10"}, "stop_errand", None)
    said = [kw["extra"]["key"] for label, kw in broken_jev if "unreadable" in label]
    assert said == ["screen_action", "stop_errand"], said
