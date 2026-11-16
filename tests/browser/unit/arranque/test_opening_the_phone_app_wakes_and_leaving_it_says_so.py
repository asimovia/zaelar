"""Opening the app on his phone wakes the agent, and leaving it says so (node 4.553).

Measured by the operator (2026-11-16): the phone app found the agent asleep and asked him to press a button. In the app
— the native companion or the page installed on the home screen — coming to the foreground is the gesture
(`frontend/app/services/presence.js::installedApp`), and leaving it is said (`POST /api/screens/beat {left}`), from which
the idle stop counts its short window (`nucleo/idle_stop.decide`, `voice/screens.left`) unless a voice session is open.
A browser tab keeps the rule that becoming visible is not a person.

Disarmed (seen red): the foreground no longer counted as input in the app → the `.mjs` fails; `decide` ignoring
`left_ms` → the engine waits the whole window; `screens.left` marking a leave with another screen on → it would sleep
under someone.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_opening_the_phone_app_wakes_and_leaving_it_says_so.mjs")
MIN = 60_000
T0 = 1_800_000_000_000


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.parametrize("mode", ["app", "pwa", "tab"])
def test_the_foreground_is_a_gesture_in_the_app_and_only_there(mode):
    r = subprocess.run(["node", str(SCRIPT), mode], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def _decide(**kw):
    from nucleo import idle_stop
    base = dict(now_ms=T0 + 20 * MIN, last_real_ms=T0, started_ms=T0 - 60 * MIN, workers_active=False, next_due_s=None,
                window_ms=15 * MIN, last_presence_ms=T0, grace_ms=1 * MIN)
    base.update(kw)
    pos = [base.pop(k) for k in ("now_ms", "last_real_ms", "started_ms", "workers_active", "next_due_s", "window_ms")]
    return idle_stop.decide(*pos, **base)


def test_the_engine_sleeps_a_short_window_after_he_left_not_a_whole_one():
    # he was present at T0 and left one minute later; three minutes on, the whole window (15) has not passed
    assert _decide(now_ms=T0 + 4 * MIN) is None, "without a leave the whole window holds"
    why = _decide(now_ms=T0 + 4 * MIN, left_ms=T0 + 1 * MIN)
    assert why and "left" in why, "he said he is gone: the short window counts from that moment"
    assert _decide(now_ms=T0 + 90_000, left_ms=T0 + 1 * MIN) is None, "…but not before the short window has passed"


def test_work_and_what_is_due_keep_their_veto_after_he_left():
    left = dict(now_ms=T0 + 4 * MIN, left_ms=T0 + 1 * MIN)
    assert _decide(**left, workers_active=True) is None, "a task in progress keeps the engine up"
    assert _decide(**left, next_due_s=(T0 + 6 * MIN) / 1000) is None, "a scheduled notice due soon keeps it up"
    assert _decide(**left, last_real_ms=T0 + 3 * MIN + 30_000) is None, "real activity after he left restarts the short window"


def test_coming_back_cancels_the_leave():
    # present again after leaving: the leave is older than his presence, so the whole window holds
    assert _decide(now_ms=T0 + 6 * MIN, left_ms=T0 + 1 * MIN, last_presence_ms=T0 + 2 * MIN) is None


@pytest.fixture
def screens():
    from voice import screens as s
    s._reset_for_tests()
    s._input["at"] = s._presence["at"] = 0.0
    yield s
    s._reset_for_tests()
    s._input["at"] = s._presence["at"] = 0.0


def test_a_leave_counts_only_when_no_other_screen_is_on_and_until_someone_is_present(screens):
    screens.attach("mobile:aa")
    screens.present("mobile:aa")
    screens.left("mobile:aa")
    assert screens.last_left_ms() is not None, "the only screen was put away: nobody is there"
    screens.present("mobile:aa")
    assert screens.last_left_ms() is None, "he came back: the leave no longer speaks"
    screens.attach("desktop:bb")
    screens.present("desktop:bb")
    screens.left("mobile:aa")
    assert screens.last_left_ms() is None, "the phone was put away with the computer's page on: someone is still there"


def test_the_beat_carries_the_leave_and_a_visible_beat_is_never_one(screens):
    from server import screens_api
    screens.attach("mobile:aa")
    screens_api.beat({"dev": "mobile:aa", "visible": True, "left": True})
    assert screens.last_left_ms() is None, "a screen that says it is visible has not left"
    screens_api.beat({"dev": "mobile:aa", "visible": False, "left": True})
    assert screens.last_left_ms() is not None


def test_a_voice_session_open_is_not_someone_gone(screens, monkeypatch):
    from nucleo import idle_stop
    screens.attach("mobile:aa")
    screens.left("mobile:aa")
    assert idle_stop._left() is not None
    monkeypatch.setattr(screens, "has_session", lambda: True)
    assert idle_stop._left() is None, "he put the phone in his pocket with the voice on: the whole window holds"
