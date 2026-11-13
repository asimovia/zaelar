"""The markets card says which quote and which period each screen charts (V2-884 C8 step 5).

A shared app moved only by orders (the range tabs go through the same `range` action the voice uses): the report is
what makes «the chart on your phone still shows the last month» sayable — a `show` or a `range` is `?ordered` on each
screen until that screen has drawn it. The card says `symbol` ("" = nothing charted) and `range` after every paint.
Two screen pairs; the rendered card through the real reporter into the real door. No network: the store is written
as the fetch would leave it. Disarms (named in the test): the card that never reports → `state unreported`; `range`
following only `range` → a new quote reads as the old period confirmed.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from voice import screens
from widgets import state, state_decl, state_render, store
from tests.browser.unit.widgets.state_card import card_page, deliver, mount, posts, push, settle  # noqa: F401

ENGINE = pathlib.Path(__file__).resolve().parents[4]
PAIRS = [("desktop:aaa", "mobile:bbb"), ("desktop:aaa", "desktop:bbb")]
QUOTE = {"symbol": "^IBEX", "name": "IBEX 35", "range": "1mo", "currency": "EUR", "exchange": "MCE", "price": 11000.0,
         "change": 10.0, "change_pct": 0.1, "points": [[1_790_000_000, 10990.0], [1_790_086_400, 11000.0]],
         "fetched_at": 1_790_086_400.0, "as_of": 1_790_086_400, "error": "", "failed": ""}


@pytest.fixture
def mk(tmp_path, monkeypatch):
    from server import canvas_api
    from widgets.markets import data
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    state._reset_for_tests()
    screens._reset_for_tests()
    store.save("markets", dict(QUOTE))

    def on(a, b):
        for d in (a, b):
            screens.attach(d)
        monkeypatch.setattr(canvas_api, "_BY_DEV", {a: {"open": ["markets"]}, b: {"open": ["markets"]}})
    yield data, on
    state._reset_for_tests()
    screens._reset_for_tests()


def _say(dev, n, full=False, **fields):
    return state.report("markets", {"dev": dev, "mount": "m1", "n": n, "full": full or n == 1, "patch": fields,
                                    "ack": state.stamp("markets")})[0]


def test_markets_declares_its_state_and_it_is_shared():
    man = json.loads((ENGINE / "widgets/markets/manifest.json").read_text())
    assert man["screens"] == "shared" and state_decl.problem(man) is None and "adopt" not in json.dumps(man["state"])


@pytest.mark.parametrize("a,b", PAIRS)
def test_two_screens_each_its_chart_and_a_new_quote_waits_for_each_ack(mk, a, b):
    _data, on = mk
    on(a, b)
    assert state_render.clause("markets") == "markets: state unreported"
    assert _say(a, 1, symbol="^IBEX", range="1mo") == 200 and _say(b, 1, symbol="^IBEX", range="1y") == 200
    assert state_render.clause("markets", dev=a).endswith(': symbol="^IBEX", range=1mo')
    assert state_render.clause("markets", dev=b).endswith(': symbol="^IBEX", range=1y')
    store.save("markets", {**QUOTE, "symbol": "BTC-USD", "name": "Bitcoin"})          # a show: same period, new quote
    for d in (a, b):
        assert "range=?ordered" in state_render.clause("markets", dev=d), f"a new quote read as charted on {d}"
    assert _say(a, 2, full=True, symbol="BTC-USD", range="1mo") == 200
    assert state_render.clause("markets", dev=a).endswith(': symbol="BTC-USD", range=1mo')
    assert "=?ordered" in state_render.clause("markets", dev=b), "one screen's ack confirmed the other"


def test_the_rendered_chart_says_its_quote_and_period_through_the_door(mk, card_page):
    data, on = mk
    a, b = PAIRS[0]
    on(a, b)
    mount(card_page, "markets", {**data.view_data(), "_rev": state.stamp("markets")}, a)
    sent = posts(card_page)
    assert sent and sent[0]["full"] and sent[0]["patch"] == {"symbol": "^IBEX", "range": "1mo"}, sent
    deliver("markets", sent)
    store.save("markets", {**QUOTE, "range": "5y"})                                   # the period he asked for
    push(card_page, {**data.view_data(), "_rev": state.stamp("markets")})
    deliver("markets", posts(card_page))
    assert state_render.clause("markets", dev=a).endswith(': symbol="^IBEX", range=5y'), \
        state_render.clause("markets", dev=a)
    after = state_render.clause("markets", dev=a)                       # the dust settles (step-5 audit P1-1)
    settle(card_page, "markets")
    assert state_render.clause("markets", dev=a) == after, "a previous paint spoke after the last one"
