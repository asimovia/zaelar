"""V2-901 — a ride is recorded from the device bridge's sample batches exactly as the source app did on each fix.

One screen owns the ride (a stranger's batch is refused); the 5-s GPS countdown and 2 s more only calibrate; a fix
worse than 30 m or implying over 80 km/h is dropped; a batch sent twice counts once; a pause is an interval of
TIME, so samples that arrive late are judged by when they were taken; a trackpoint is kept every 5 s with the heart
rate of that moment (none without a strap — never a zero); a GPS blackout over 30 s is rebuilt along the road, or
counted straight when no road is found; saving closes the ride with its summary, discarding deletes its track.
"""
from __future__ import annotations

import os

import pytest

from tests.browser.unit.cycling.conftest import loc, ride_samples
from widgets.cycling import net, tracks


@pytest.fixture
def clock(monkeypatch, cyc):
    import time as _time
    now = [1_800_000_000_000.0]
    monkeypatch.setattr(_time, "time", lambda: now[0] / 1000.0)
    return now


def _start(cyc, owner="phone"):
    r = cyc.apply_action("start", {})
    assert r["ok"] and r["status"] == "running"
    assert cyc.apply_action("claim", {"owner": owner})["ok"]
    return cyc._load()["current"]


def test_one_screen_owns_the_ride(cyc, clock):
    cur = _start(cyc)
    assert cyc.apply_action("claim", {"owner": "laptop"}).get("owned_by_another_screen")
    batch, _, _ = ride_samples(cur["warmup_until_ms"] + 1000, 10)
    assert cyc.apply_action("samples", {"owner": "laptop", "samples": batch}).get("owned_by_another_screen")
    assert cyc.view_data()["current"]["has_location"] is False


def test_the_countdown_only_calibrates_and_a_retry_counts_once(cyc, clock):
    cur = _start(cyc)
    warm, lat, seq = ride_samples(cur["countdown_until_ms"] - 5000, 7)          # countdown + warm-up: nothing counts
    cyc.apply_action("samples", {"owner": "phone", "samples": warm})
    v = cyc.view_data()["current"]
    assert v["distance_km"] == 0 and v["route"] == [] and not os.path.exists(tracks.path(cur["id"]))
    batch, _, _ = ride_samples(cur["warmup_until_ms"] + 1000, 120, lat0=lat, seq0=seq)
    cyc.apply_action("samples", {"owner": "phone", "samples": batch})
    once = cyc.view_data()["current"]
    assert 0.69 <= once["distance_km"] <= 0.72, once["distance_km"]             # 119 s at 6 m/s
    assert 20 < once["speed_kmh"] < 23 and once["max_speed_kmh"] >= once["speed_kmh"]
    n = len(tracks.load(cur["id"]))
    assert 19 <= n <= 21, n                         # one trackpoint once MORE than 5 s passed: every 6 s at 1 Hz
    cyc.apply_action("samples", {"owner": "phone", "samples": batch})          # the retry after the locked screen
    assert cyc.view_data()["current"]["distance_km"] == once["distance_km"] and len(tracks.load(cur["id"])) == n


def test_a_bad_fix_and_a_jump_are_dropped(cyc, clock):
    cur = _start(cyc)
    t = cur["warmup_until_ms"] + 1000
    batch, lat, seq = ride_samples(t, 20, hr=None)
    batch += [loc(seq + 1, t + 20_000, lat + 0.0090, 2.10, acc=5),               # 1 km in one second: a GPS jump
              loc(seq + 2, t + 21_000, lat + 0.0002, 2.10, acc=45)]              # 45 m accuracy: not trusted
    cyc.apply_action("samples", {"owner": "phone", "samples": batch})
    v = cyc.view_data()["current"]
    assert 0.10 <= v["distance_km"] <= 0.12, v["distance_km"]
    assert v["heart_rate"] is None and not v["has_heart_rate"]                  # no strap: no reading, not a zero
    assert all(p["heart_rate"] is None for p in tracks.load(cur["id"]))


def test_a_pause_is_judged_by_when_each_sample_was_taken(cyc, clock):
    cur = _start(cyc)
    t = cur["warmup_until_ms"] + 1000
    clock[0] = t + 60_000
    cyc.apply_action("pause", {})
    clock[0] = t + 120_000
    cyc.apply_action("resume", {})
    batch, _, _ = ride_samples(t, 180)                                          # arrives AFTER the pause ended
    cyc.apply_action("samples", {"owner": "phone", "samples": batch})
    v = cyc.view_data()["current"]
    assert 0.70 <= v["distance_km"] <= 0.73, v["distance_km"]                  # 2 of the 3 minutes count
    assert v["paused"] is False and 60 <= v["elapsed_s"] <= 66, v["elapsed_s"]  # riding time leaves the pause out


def test_a_blackout_is_rebuilt_along_the_road_or_counted_straight(cyc, clock, monkeypatch):
    cur = _start(cyc)
    t = cur["warmup_until_ms"] + 1000
    a, lat, seq = ride_samples(t, 20)
    b, _, _ = ride_samples(t + 80_000, 20, lat0=lat + 0.0027, seq0=seq)        # 60 s blind, ~300 m further
    road = {"distance_m": 420.0, "duration_sec": 60,
            "coordinates": [[2.10, lat], [2.1015, lat + 0.0013], [2.10, lat + 0.0027]]}
    monkeypatch.setattr(net, "route", lambda frm, to, profile="cycling", timeout=2.5: road)
    cyc.apply_action("samples", {"owner": "phone", "samples": a + b})
    v = cyc.view_data()["current"]
    assert any(e["kind"] == "gap_rebuilt" for e in v["events"])
    rebuilt = [p for p in tracks.load(cur["id"]) if p["source"] == "reconstructed"]
    assert len(rebuilt) >= 10 and v["reconstructed"] == len(rebuilt)
    assert 0.64 <= v["distance_km"] <= 0.66, v["distance_km"]   # 2×114 m ridden + 420 m of road, the gap counted ONCE
    cyc.apply_action("stop", {})
    cur = _start(cyc)
    t = cur["warmup_until_ms"] + 1000
    monkeypatch.setattr(net, "route", lambda *a, **k: None)                    # no road found
    a, lat, seq = ride_samples(t, 20)
    b, _, _ = ride_samples(t + 80_000, 20, lat0=lat + 0.0027, seq0=seq)
    cyc.apply_action("samples", {"owner": "phone", "samples": a + b})
    v = cyc.view_data()["current"]
    assert any(e["kind"] == "gap_straight" for e in v["events"]) and 0.52 <= v["distance_km"] <= 0.54


def test_save_keeps_the_summary_and_discard_deletes_the_track(cyc, clock):
    cur = _start(cyc)
    batch, _, _ = ride_samples(cur["warmup_until_ms"] + 1000, 300, hr=140)
    cyc.apply_action("samples", {"owner": "phone", "samples": batch})
    r = cyc.apply_action("stop", {})
    s = r["summary"]
    assert r["status"] == "idle" and s["status"] == "done" and 1.7 <= s["distance_km"] <= 1.8
    assert s["avg_hr"] == 140 and s["max_hr"] == 140 and 300 <= s["duration_sec"] <= 303   # from the countdown's end
    assert s["avg_speed_kmh"] is not None and s["start_lat"] is not None
    v = cyc.view_data()
    assert v["status"] == "idle" and v["rides"][0]["id"] == cur["id"] and v["ui"]["view"] == "history"
    cur = _start(cyc)
    cyc.apply_action("samples", {"owner": "phone", "samples": ride_samples(cur["warmup_until_ms"] + 1000, 30)[0]})
    assert os.path.exists(tracks.path(cur["id"]))
    assert cyc.apply_action("discard", {})["discarded"] == cur["id"]
    assert not os.path.exists(tracks.path(cur["id"])) and [x["id"] for x in cyc.view_data()["rides"]] == [s["id"]]
