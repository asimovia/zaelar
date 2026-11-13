"""The timer's phase is what each screen's countdown shows, not what the store last said (V2-884 C8 step 5).

The countdown runs IN the card (and a page restored from localStorage can resume one the store forgot), so the store's
`running` and the screen disagree the second the count reaches zero: the brain read «running» over a timer that had
already rung. The card says `phase` (idle · running · paused · finished) and `label` after every paint; an order that
moves it (`set`, `pause`, `start`, `reset`) is `?ordered` on each screen until that screen acks it. Two screen pairs;
the rendered card through the real reporter into the real door. Disarms (named in the test): the card that never
reports → `state unreported`; the phase following only `running` → a new `set` while running reads as confirmed.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from voice import screens
from widgets import state, state_decl, state_render, store
from tests.browser.unit.widgets.state_card import card_page, deliver, mount, posts  # noqa: F401

ENGINE = pathlib.Path(__file__).resolve().parents[4]
PAIRS = [("desktop:aaa", "mobile:bbb"), ("desktop:aaa", "desktop:bbb")]


@pytest.fixture
def timer(tmp_path, monkeypatch):
    from server import canvas_api
    from widgets.timer import data
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    state._reset_for_tests()
    screens._reset_for_tests()
    data.apply_action("set", {"seconds": 300, "label": "pasta"})

    def on(a, b):
        for d in (a, b):
            screens.attach(d)
        monkeypatch.setattr(canvas_api, "_BY_DEV", {a: {"open": ["timer"]}, b: {"open": ["timer"]}})
    yield data, on
    state._reset_for_tests()
    screens._reset_for_tests()


def _say(dev, n, full=False, **fields):
    return state.report("timer", {"dev": dev, "mount": "m1", "n": n, "full": full or n == 1, "patch": fields,
                                  "ack": state.stamp("timer")})[0]


def test_the_timer_declares_its_state_and_it_is_shared():
    man = json.loads((ENGINE / "widgets/timer/manifest.json").read_text())
    assert man["screens"] == "shared" and state_decl.problem(man) is None and "adopt" not in json.dumps(man["state"])


@pytest.mark.parametrize("a,b", PAIRS)
def test_two_screens_each_its_phase_and_an_order_waits_for_each_ack(timer, a, b):
    data, on = timer
    on(a, b)
    assert state_render.clause("timer") == "timer: state unreported"
    assert _say(a, 1, phase="running", label="pasta") == 200 and _say(b, 1, phase="finished", label="pasta") == 200
    assert state_render.clause("timer", dev=a).endswith(': phase=running, label="pasta"')
    assert state_render.clause("timer", dev=b).endswith(': phase=finished, label="pasta"')
    data.apply_action("set", {"seconds": 600, "label": "pasta"})             # running → running: only the target moves
    for d in (a, b):
        assert "phase=?ordered" in state_render.clause("timer", dev=d), f"a new set read as confirmed on {d}"
    assert _say(a, 2, full=True, phase="running", label="pasta") == 200
    assert "phase=?ordered" not in state_render.clause("timer", dev=a)
    assert "phase=?ordered" in state_render.clause("timer", dev=b), "one screen's ack confirmed the other"


def test_the_rendered_countdown_says_finished_when_it_reaches_zero(timer, card_page):
    data, on = timer
    a, b = PAIRS[0]
    on(a, b)
    card_page.goto(card_page._hb_origin + "/widgets/timer/")
    card_page.evaluate("() => localStorage.clear()")
    shown = {**data.view_data(), "remaining": 1, "_rev": state.stamp("timer")}   # one second left on this screen
    mount(card_page, "timer", shown, a)
    first = posts(card_page)
    assert first and first[0]["full"] and first[0]["patch"] == {"phase": "running", "label": "pasta"}, first
    deliver("timer", first)
    card_page.wait_for_timeout(1300)                                          # the card's own tick reaches zero
    later = posts(card_page)
    deliver("timer", later)
    assert any(p["patch"].get("phase") == "finished" for p in later), later
    assert state_render.clause("timer", dev=a).endswith(': phase=finished, label="pasta"'), \
        "the screen rang and the line still said running"
