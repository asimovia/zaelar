"""The activity card says whether an activity runs, which one, and WHERE it is recorded (V2-884 C8 step 5 + audit P2-2).

An activity is read by ONE screen. The card paints three places — recording here, recording on your other screen,
waiting for the screen that records it — and the report says the same: `recorder` = `here` (a LIVE sensor session on
this screen, never a bare claim: a claim whose sensors failed reads nothing), `elsewhere` (another screen claimed it),
`none`. «Is my phone recording?» is a screen's answer. The card repaints when its session starts or fails. A `start`/
`stop` is `?ordered` on each screen until it acks. The rendered card runs the REAL path: his tap → `start` → the claim
through the app's own `apply_action` → the stand-in device's session. Disarms (named in the test): the card that never
reports → `state unreported`; `here` on a claim with no session → a failed sensor reads as recording; `elsewhere`
lost → the other screen's recording reads as nobody; no repaint when the session starts → the line keeps «none».
"""
from __future__ import annotations

import json
import pathlib

import pytest

from voice import screens
from widgets import state, state_decl, state_render, store
from tests.browser.unit.widgets.state_card import card_page, mount, push, settle  # noqa: F401

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
    for d in (a, b):
        assert _say(d, 1, phase="idle", kind="none", recorder="none") == 200
    assert data.apply_action("start", {"kind": "cycling"})["ok"]
    for d in (a, b):
        assert "phase=?ordered" in state_render.clause("activity", dev=d), f"a start read as shown on {d}"
    assert _say(b, 2, full=True, phase="running", kind="cycling", recorder="here") == 200
    assert _say(a, 2, full=True, phase="running", kind="cycling", recorder="elsewhere") == 200
    assert state_render.clause("activity", dev=b).endswith(": phase=running, kind=cycling, recorder=here")
    assert state_render.clause("activity", dev=a).endswith(": phase=running, kind=cycling, recorder=elsewhere")


def _push(page, data):
    push(page, {**data.view_data(), "_rev": state.stamp("activity")})
    return settle(page, "activity")


def test_his_tap_records_here_once_the_sensors_run(act, card_page):
    data, on = act
    a, b = PAIRS[0]
    on(a, b)
    mount(card_page, "activity", {**data.view_data(), "_rev": state.stamp("activity")}, a, act=True,
          device={"sensors": {"location": {"available": True}}}, session=True)
    settle(card_page, "activity")
    assert state_render.clause("activity", dev=a).endswith(": at rest")
    card_page.click(".ac-kinds .ac-btn")                                              # his tap: «Ride»
    card_page.wait_for_timeout(300)
    _push(card_page, data)                                                            # the start lands; the claim runs
    assert data.view_data().get("owner"), "the tap never reached the claim"
    _push(card_page, data)                                                            # the claim lands
    assert state_render.clause("activity", dev=a).endswith(": phase=running, kind=cycling, recorder=here"), \
        state_render.clause("activity", dev=a)
    assert "Recording on this screen" in card_page.inner_text("#w")


def test_a_claim_whose_sensors_fail_is_not_recording(act, card_page):
    data, on = act
    a, b = PAIRS[0]
    on(a, b)
    mount(card_page, "activity", {**data.view_data(), "_rev": state.stamp("activity")}, a, act=True,
          device={"sensors": {}}, session=False, device_error="permission denied")
    card_page.click(".ac-kinds .ac-btn")
    card_page.wait_for_timeout(300)
    _push(card_page, data)
    _push(card_page, data)
    line = state_render.clause("activity", dev=a)
    assert line.endswith(": phase=running, kind=cycling") and "recorder=here" not in line, line
    assert "cannot read the sensors" in card_page.inner_text("#w"), "the card still painted «recording here»"


def test_another_screens_recording_reads_elsewhere(act, card_page):
    data, on = act
    a, b = PAIRS[0]
    on(a, b)
    assert data.apply_action("start", {"kind": "running"})["ok"]
    assert data.apply_action("claim", {"owner": "s-the-phone"})["ok"]                 # the phone claimed it
    mount(card_page, "activity", {**data.view_data(), "_rev": state.stamp("activity")}, a, act=True)
    settle(card_page, "activity")
    assert state_render.clause("activity", dev=a).endswith(": phase=running, kind=running, recorder=elsewhere")
    assert "Recording on your other screen" in card_page.inner_text("#w")
    data.apply_action("stop", {})
    _push(card_page, data)
    assert state_render.clause("activity", dev=a).endswith(": at rest"), state_render.clause("activity", dev=a)


def test_a_session_that_starts_after_the_claim_landed_is_said_when_it_starts(act, card_page):
    """The claim reaches the card before the sensors answer: the card paints «waiting», and when the session starts it
    repaints — the line moves to `here` with no further push."""
    data, on = act
    a, b = PAIRS[0]
    on(a, b)
    mount(card_page, "activity", {**data.view_data(), "_rev": state.stamp("activity")}, a, act=True,
          device={"sensors": {"location": {"available": True}}}, session=True, session_delay=600)
    card_page.click(".ac-kinds .ac-btn")
    card_page.wait_for_timeout(200)
    push(card_page, {**data.view_data(), "_rev": state.stamp("activity")})          # the start: the claim runs
    card_page.wait_for_timeout(200)
    push(card_page, {**data.view_data(), "_rev": state.stamp("activity")})          # the claim lands, no session yet
    settle(card_page, "activity", 1500)
    assert state_render.clause("activity", dev=a).endswith(", recorder=here"), state_render.clause("activity", dev=a)
