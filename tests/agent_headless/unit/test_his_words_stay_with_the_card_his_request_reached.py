"""His words stay with the card his request already acted on (V2-831 T-19, V2-879 O1).

The one relay door into a running errand (`dispatch.relay_his_words`) refuses his sentence when the request went
through a card's door (`consequence.reached("widget.data", "music")`): the errand running behind that card is neither
steered nor stopped by an order that was the card's. With no card reached, his words reach the errand.
"""
from __future__ import annotations

import pytest

from nucleo import consequence, dispatch
from nucleo.dispatch import soon
from voice import trace


@pytest.fixture
def sent(monkeypatch):
    got = []
    monkeypatch.setattr(dispatch, "inject_soon", lambda which, words: got.append((which, words)))
    monkeypatch.setattr(consequence, "_REACHED", {})
    yield got
    trace.adopt("")


@pytest.mark.parametrize("door", ["widget.data", "music"])
def test_a_card_his_request_reached_keeps_his_words(sent, door):
    trace.adopt("t-card")
    consequence._REACHED["t-card"] = {door}
    assert soon.relay_his_words("1", "w_put those on the map") is False
    assert sent == [], "the relay door sent a card's order to the running errand"


def test_with_no_card_reached_his_words_reach_the_errand(sent):
    trace.adopt("t-free")
    consequence._REACHED["t-other"] = {"widget.data"}
    assert soon.relay_his_words("1", "w_only the cheap ones") is True
    assert sent == [("1", "w_only the cheap ones")]
