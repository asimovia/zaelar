"""The activity card says whether an activity runs, which one, and whether THIS screen records it (V2-884 C8 step 5).

An activity is read by ONE screen (the one that claimed the sensors); every other screen shows it «recording on your
other screen». «Is my phone recording?» is a screen's answer. The card says `phase`, `kind` and `recording` after every
paint; a `start`/`stop` is `?ordered` on each screen until it acks. Two screen pairs; the rendered card through the real
reporter into the real door. Disarms (named in the test): the card that never reports → `state unreported`; `kind`
without its `none` rest → an ended ride is not at rest.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from voice import screens
from widgets import state, state_decl, state_render, store
from tests.browser.unit.widgets.state_card import card_page, deliver, mount, posts, push  # noqa: F401

ENGINE = pathlib.Path(__file__).resolve().parents[4]
PAIRS = [("desktop:aaa", "mobile:bbb"), ("desktop:aaa", "desktop:bbb")]


@pytest.fixture
def act(tmp_path, monkeypatch):
    from server import canvas_api
    from widgets.activity import data
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    state._reset_for_tests()
    screens._reset_for_tests()
    data.view_data()

    def on(a, b):
        for d in (a, b):
            screens.attach(d)
        monkeypatch.setattr(canvas_api, "_BY_DEV", {a: {"open": ["activity"]}, b: {"open": ["activity"]}})
    yield data, on
    state._reset_for_tests()
    screens._reset_for_tests()


def _say(dev, n, full=False, **fields):
    return state.report("activity", {"dev": dev, "mount": "m1", "n": n, "full": full or n == 1, "patch": fields,
                                     "ack": state.stamp("activity")})[0]


def test_the_activity_declares_its_state_and_it_is_shared():
    man = json.loads((ENGINE / "widgets/activity/manifest.json").read_text())
    assert man["screens"] == "shared" and state_decl.problem(man) is None and "adopt" not in json.dumps(man["state"])


@pytest.mark.parametrize("a,b", PAIRS)
def test_two_screens_one_records_and_a_start_waits_for_each_ack(act, a, b):
    data, on = act
    on(a, b)
    assert state_render.clause("activity") == "activity: state unreported"
    assert data.apply_action("start", {"kind": "cycling"})["ok"]
    for d in (a, b):
        assert _say(d, 1, phase="idle", recording=False) == 200
    assert _say(b, 2, full=True, phase="running", kind="cycling", recording=True) == 200
    assert _say(a, 2, full=True, phase="running", kind="cycling", recording=False) == 200
    assert state_render.clause("activity", dev=b).endswith(": phase=running, kind=cycling, recording")
    assert state_render.clause("activity", dev=a).endswith(": phase=running, kind=cycling")
    assert data.apply_action("stop", {}).get("ok") is not False
    for d in (a, b):
        assert "phase=?ordered" in state_render.clause("activity", dev=d), f"a stop read as shown on {d}"


def test_the_rendered_card_says_its_activity_through_the_door(act, card_page):
    data, on = act
    a, b = PAIRS[0]
    on(a, b)
    mount(card_page, "activity", {**data.view_data(), "_rev": state.stamp("activity")}, a)
    sent = posts(card_page)
    assert sent and sent[0]["full"] and sent[0]["patch"] == {"phase": "idle", "kind": "none", "recording": False}, sent
    deliver("activity", sent)
    data.apply_action("start", {"kind": "running"})                                    # the voice: a run
    push(card_page, {**data.view_data(), "_rev": state.stamp("activity")})
    deliver("activity", posts(card_page))
    assert state_render.clause("activity", dev=a).endswith(": phase=running, kind=running"), \
        state_render.clause("activity", dev=a)
    data.apply_action("stop", {})
    push(card_page, {**data.view_data(), "_rev": state.stamp("activity")})
    deliver("activity", posts(card_page))
    assert state_render.clause("activity", dev=a).endswith(": at rest"), state_render.clause("activity", dev=a)
