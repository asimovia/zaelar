"""V2-898 — Activity as a stable base app: what it stores and says never claims a reading it lacks.

A drive with no GPS keeps no distance (not 0 km), a phone with no barometer reports no climb (not 0 m), and the
digest says «no GPS fix yet» instead of «0.0 km». At rest the digest carries the last activities, so «what did I do
yesterday?» needs no round trip. The live heart-rate sparkline and the 7-day bars come only from what is stored. The
card's half (claims, failures, locale, charts, strap) is the .mjs next to this file.
A start reads the kind as the model wrote it (`type`, a short word) and, with none, asks — never a default ride.
Disarms: climb back to `round(0.0)`; the `cycling` default back; the summary keeping `distance_m` 0; the digest
printing `0.0 km`; the idle digest empty; `hr_recent`/`days` missing from the view.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import pytest

from widgets import store
from widgets.activity import data as act


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    yield


def _start(kind="driving"):
    assert act.apply_action("start", {"kind": kind})["ok"]
    assert act.apply_action("claim", {"owner": "phone"})["ok"]


def test_no_gps_and_no_barometer_are_no_reading_never_a_zero():
    _start("driving")
    v = act.view_data()
    assert v["climb_m"] is None, "a phone with no barometer reported a climb"
    assert "no GPS fix yet" in act.prompt_digest() and "0.0 km" not in act.prompt_digest()
    s = act.apply_action("stop", {})["summary"]
    assert s["distance_m"] is None and s["climb_m"] is None, s
    assert act.view_data()["days"] == [], "a drive with no distance fed the 7-day bars"


def test_a_barometer_climb_and_a_gps_distance_are_kept():
    _start("cycling")
    now = int(time.time() * 1000)
    act.apply_action("samples", {"owner": "phone", "samples": [
        {"seq": 1, "kind": "altitude", "t": now, "relative_m": 0.0},
        {"seq": 2, "kind": "altitude", "t": now, "relative_m": 12.0},
        {"seq": 3, "kind": "location", "t": now, "lat": 41.39, "lon": 2.17, "accuracy_m": 5},
        {"seq": 4, "kind": "location", "t": now + 30_000, "lat": 41.3909, "lon": 2.17, "accuracy_m": 5}]})
    assert act.view_data()["climb_m"] == 12
    s = act.apply_action("stop", {})["summary"]
    assert 95 <= s["distance_m"] <= 105 and s["climb_m"] == 12
    days = act.view_data()["days"]
    assert len(days) == 1 and days[0][1] == s["distance_m"]


def test_the_heart_rate_sparkline_is_the_last_minutes_only():
    _start("running")
    now = time.time()
    old = [{"seq": i, "kind": "heart_rate", "t": int((now - 1200 + i) * 1000), "bpm": 100} for i in range(5)]
    new = [{"seq": 100 + i, "kind": "heart_rate", "t": int((now - 300 + i * 2) * 1000), "bpm": 120 + i % 20} for i in range(150)]
    act.apply_action("samples", {"owner": "phone", "samples": old + new})
    pts = act.view_data()["hr_recent"]
    assert 2 <= len(pts) <= act.HR_SPARK_POINTS, len(pts)
    assert all(p[1] >= 120 for p in pts), "readings older than the window reached the sparkline"


def test_at_rest_the_digest_says_the_last_activities():
    assert act.prompt_digest() == "", "an empty history still costs the prompt a line"
    _start("walking")
    act.apply_action("stop", {})
    d = act.prompt_digest()
    assert d.startswith("Activity on screen: nothing recording. Last: walking"), d
    assert "no distance" in d


@pytest.mark.parametrize("payload,kind", [({"type": "walk"}, "walking"), ({"kind": "run"}, "running"),
                                          ({"kind": "bici"}, "cycling"), ({"activity": "Driving"}, "driving")])
def test_a_start_reads_the_kind_as_the_model_wrote_it(payload, kind):
    """Measured on the live engine (V2-898 T7): «I'm going for a walk» arrived as `{"type": "walk"}`."""
    assert act.apply_action("start", payload)["kind"] == kind


def test_a_start_with_no_kind_asks_instead_of_recording_a_ride():
    """Measured (V2-898 T7): «empiezo a correr» arrived with no payload: the app would have recorded a ride."""
    r = act.apply_action("start", {})
    assert not r["ok"] and r["error"] == "kind_required" and "running" in r["kinds"]
    assert act.view_data()["status"] == "idle"


def test_an_unknown_action_answers_the_house_error():
    r = act.apply_action("teleport", {})
    assert r["error"] == "unknown_action" and "start" in r["actions"]


def test_the_card_half():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required")
    script = Path(__file__).with_name("test_the_activity_card_is_a_stable_base_app.mjs")
    r = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr
