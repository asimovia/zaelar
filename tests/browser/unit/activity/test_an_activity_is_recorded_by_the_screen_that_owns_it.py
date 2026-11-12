"""V2-890 F1 — an activity he starts is recorded by ONE screen, and its figures never claim a reading we lack.

The sensors are read by the screen that claims the activity (the phone app, or the screen where he tapped Start);
every other screen reflects data.py. A batch from a screen that does not own it is refused, a batch sent twice (a
retry when the locked phone comes back) counts once, GPS jitter is not distance, and with no strap the heart rate is
`None` — never a zero. The card's own half (who claims, the locked-screen handover) is the .mjs next to this file.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import pytest

from widgets.activity import data as act

T0 = 1_800_000_000_000


def _loc(seq, lat, lon, dt_s, acc=5.0):
    return {"seq": seq, "kind": "location", "t": T0 + dt_s * 1000, "lat": lat, "lon": lon, "accuracy_m": acc, "speed_mps": 6.0}


@pytest.fixture(autouse=True)
def _fresh():
    act.apply_action("stop", {})
    yield
    act.apply_action("stop", {})


def test_one_screen_owns_the_activity_and_a_strangers_batch_is_refused():
    assert act.apply_action("start", {"kind": "cycling"})["status"] == "running"
    assert act.apply_action("claim", {"owner": "phone"})["ok"]
    assert act.apply_action("claim", {"owner": "laptop"}).get("owned_by_another_screen")
    r = act.apply_action("samples", {"owner": "laptop", "samples": [_loc(1, 41.39, 2.17, 0)]})
    assert r.get("owned_by_another_screen") and not act.view_data()["has_location"]


def test_a_batch_sent_twice_counts_once_and_jitter_is_not_distance():
    act.apply_action("start", {"kind": "running"})
    act.apply_action("claim", {"owner": "phone"})
    batch = [_loc(1, 41.3900, 2.1700, 0), _loc(2, 41.3900, 2.17001, 1),     # ~0.8 m: jitter
             _loc(3, 41.3909, 2.1700, 30), _loc(4, 41.3950, 2.1700, 60, acc=400)]   # a 400 m-accuracy fix: not distance
    act.apply_action("samples", {"owner": "phone", "samples": batch})
    once = act.view_data()["distance_m"]
    act.apply_action("samples", {"owner": "phone", "samples": batch})      # the retry after the locked screen
    v = act.view_data()
    assert v["distance_m"] == once and 95 <= once <= 105, once
    assert len(v["route"]) == 4


def test_no_strap_is_no_reading_never_a_zero_and_a_strap_is_now():
    act.apply_action("start", {"kind": "cycling"})
    act.apply_action("claim", {"owner": "phone"})
    v = act.view_data()
    assert v["heart_rate"] is None and v["hr_avg"] is None and not v["has_heart_rate"]
    assert "no heart-rate strap" in act.prompt_digest()
    now = int(time.time() * 1000)
    act.apply_action("samples", {"owner": "phone", "samples": [
        {"seq": 1, "kind": "heart_rate", "t": now - 2000, "bpm": 120},
        {"seq": 2, "kind": "heart_rate", "t": now, "bpm": 140}]})
    v = act.view_data()
    assert (v["heart_rate"], v["hr_avg"], v["hr_max"]) == (140, 130, 140)
    assert "heart rate 140 bpm" in act.prompt_digest()


def test_stop_keeps_the_summary_and_start_twice_is_one_activity():
    act.apply_action("start", {"kind": "walking", "label": "evening"})
    assert act.apply_action("start", {"kind": "cycling"}).get("already")
    s = act.apply_action("stop", {})["summary"]
    assert s["kind"] == "walking" and s["label"] == "evening"
    v = act.view_data()
    assert v["status"] == "idle" and v["history"][0]["kind"] == "walking"


def test_an_unknown_kind_teaches_the_retry():
    r = act.apply_action("start", {"kind": "swimming"})
    assert not r["ok"] and "cycling" in r["kinds"]


def test_the_card_claims_only_where_it_should_and_hands_over_on_return():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required")
    script = Path(__file__).with_name("test_an_activity_is_recorded_by_the_screen_that_owns_it.mjs")
    r = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr
