"""The messaging acts that queue an order every time they run are DECLARED on the manifest, not named in code (5.77).

The card's read-only veto (`outbound/lane.early`) refuses, before anything is queued, an act that would leave while
the exit door holds it. Which acts always leave is `"always_leaves": true` on their manifest entry, read by
`widgets.effects.always_leaves` — `compose` and `send_draft` leave too, but only sometimes (a draft may only be saved),
so they do not carry it and are answered later, where they queue.
"""
from __future__ import annotations

import pytest

from connectors import exit as door
from widgets import effects, runtime
from widgets.mensajeria.outbound import lane

DECLARED = sorted(a for a, s in (runtime.get("mensajeria") or {}).get("actions", {}).items()
                  if isinstance(s, dict) and s.get("always_leaves") is True)


def test_the_acts_that_always_leave_are_the_ones_that_queue_every_time():
    assert set(DECLARED) == {"send_to", "forward", "create_group", "leave_group"}, DECLARED
    assert all(effects.leaves("mensajeria", a) for a in DECLARED), "a mark on an act that never leaves means nothing"


@pytest.mark.parametrize("action", DECLARED)
def test_with_the_switch_on_each_declared_act_is_refused_before_it_queues(monkeypatch, action):
    monkeypatch.setenv(door.ENV, "all")
    out = lane.early(action, {"contact": "Odile Varga", "text": "hi"})
    assert out and out["ok"] is False and door.is_held(out.get("held")), out


@pytest.mark.parametrize("action", ["compose", "send_draft"])
def test_an_act_that_leaves_only_sometimes_is_not_vetoed_early(monkeypatch, action):
    monkeypatch.setenv(door.ENV, "all")
    assert effects.leaves("mensajeria", action) and not effects.always_leaves("mensajeria", action)
    assert lane.early(action, {"text": "hi"}) is None


def test_without_the_switch_nothing_is_vetoed(monkeypatch):
    monkeypatch.delenv(door.ENV, raising=False)
    assert all(lane.early(a, {"contact": "Odile Varga", "stamp": 1, "_lane": door.stamp(door.OWNER)}) is None
               for a in DECLARED)
