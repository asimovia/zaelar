"""Fixtures for the a2a suite: a controllable clock, the fake network, two agents and a row recorder."""
from __future__ import annotations

import pytest

from a2a import A2AAgent, FakeNetwork, Identity, events
from a2a.items import default_items


class Clock:
    def __init__(self, t: float = 1_800_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, s: float) -> None:
        self.t += s


class Rows(list):
    def ops(self, agent=None) -> list[str]:
        return [r["op"] for r in self if agent is None or r["agent"] == agent.me.did[8:16]]


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def rows():
    rec = Rows()
    events.add_sink(rec.append)
    yield rec
    events.remove_sink(rec.append)


@pytest.fixture
def net(clock):
    return FakeNetwork(clock=clock)


def make_agent(net, clock, tmp_path, name, answers=None, busy=None, profile=None):
    me = Identity.generate()
    t = net.transport(me.did)
    cards: list[dict] = []

    def asker(card):
        cards.append(card)
        a = (answers or {}).get(card["type"])
        return a(card) if callable(a) else a

    ag = A2AAgent(me, t, t, t, state_dir=tmp_path / name, clock=clock, asker=asker, display_name=name,
                  items=default_items(busy=busy, public_profile=profile))
    ag.cards = cards
    return ag


@pytest.fixture
def pair(net, clock, tmp_path):
    def build(a_answers=None, b_answers=None, busy=None, profile=None):
        a = make_agent(net, clock, tmp_path, "ana", a_answers)
        b = make_agent(net, clock, tmp_path, "marta", b_answers, busy=busy, profile=profile)
        return a, b
    return build


def connected(a, b):
    """A asks, B accepts (by the owner's call), both pulled."""
    a.connect(b.me.did, contact_id="marta", name="Marta")
    b.pull()
    b.accept(a.me.did, contact_id="ana", name="Ana")
    a.pull()
    return a, b
