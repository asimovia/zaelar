"""V2-901 — the ghost rider, live: entering, finishing and leaving a segment while recording, and the race against
the earlier attempts, on synthetic tracks.

He enters a segment within 35 m of its start and finishes within 35 m of its end, and the finish says his time
against the PR; four fixes in a row more than 50 m off the segment's real path void it for the rest of the ride
(never on a straight start→end line, where a curve would look off-route); a segment within 150 m is announced once;
an earlier attempt is AHEAD of him when, at his current progress, it had been riding for less time.
"""
from __future__ import annotations

from tests.browser.unit.cycling.conftest import M_PER_DEG_LAT
from widgets.cycling import ghost as G
from widgets.cycling import recorder as R

LAT0, LNG = 41.40, 2.10


def _seg(i0_m, i1_m, path=False, sid=1, pr=None):
    s = {"id": sid, "name": f"S{sid}", "start_lat": LAT0 + i0_m / M_PER_DEG_LAT, "start_lng": LNG,
         "end_lat": LAT0 + i1_m / M_PER_DEG_LAT, "end_lng": LNG, "distance_m": i1_m - i0_m, "pr_time_sec": pr}
    if path:
        s["polyline"] = [[LAT0 + m / M_PER_DEG_LAT, LNG] for m in range(i0_m, i1_m + 1, 50)]
    return s


def _ride(cur, segs, metres, dlng_m=0.0, t0=0.0, every_m=6.0):
    """Feed fixes due north every `every_m` metres (one per second), optionally `dlng_m` off to the east."""
    for k, m in enumerate(metres):
        lng = LNG + dlng_m / (M_PER_DEG_LAT * 0.75)
        G.tick(cur, segs, LAT0 + m / M_PER_DEG_LAT, lng, t0 + k * 1000)


def test_enter_and_finish_say_the_time_against_the_pr():
    cur = R.new_ride(1, 0, 120, 140)
    segs = [_seg(300, 900, pr=120)]
    _ride(cur, segs, [i * 6.0 for i in range(0, 161)])                       # 0 → 960 m at 6 m/s
    kinds = [e["kind"] for e in cur["events"]]
    assert kinds == ["approach", "enter", "finish"], kinds
    fin = cur["events"][-1]
    assert 95 <= fin["time_sec"] <= 105 and fin["delta_sec"] == fin["time_sec"] - 120   # 600 m at 6 m/s ≈ 100 s
    assert cur["ghost"]["inside"] == [] and cur["ghost"]["selected"] is None


def test_off_the_real_path_voids_the_segment_but_not_on_a_straight_line():
    real = [_seg(300, 900, path=True)]
    cur = R.new_ride(1, 0, None, None)
    _ride(cur, real, [i * 6.0 for i in range(50, 60)])                       # in, on the path
    _ride(cur, real, [i * 6.0 for i in range(60, 70)], dlng_m=80, t0=10_000)  # 80 m east for 10 fixes
    assert any(e["kind"] == "abandon" for e in cur["events"]) and 1 in cur["ghost"]["abandoned"]
    _ride(cur, real, [300 + i * 6.0 for i in range(5)], t0=30_000)          # back at the start: never re-armed
    assert not cur["ghost"]["inside"]
    straight = [_seg(300, 900)]                                              # no real path: no off-route judgement
    cur = R.new_ride(2, 0, None, None)
    _ride(cur, straight, [i * 6.0 for i in range(50, 60)])
    _ride(cur, straight, [i * 6.0 for i in range(60, 70)], dlng_m=80, t0=10_000)
    assert not any(e["kind"] == "abandon" for e in cur["events"]) and cur["ghost"]["inside"]


def test_a_rival_is_ahead_when_it_had_ridden_less_time_at_his_progress():
    active = {"entered_ms": 0, "distance_m": 600, "dist_accum": 300}          # halfway, 60 s in
    attempts = [{"id": 1, "time_sec": 100, "is_pr": 1}, {"id": 2, "time_sec": 140}]
    rv = {r["id"]: r for r in G.rivals(active, attempts, 60_000)}
    assert rv[1]["delta_sec"] == 10 and rv[1]["is_pr"]                        # the PR was at 300 m after 50 s
    assert rv[2]["delta_sec"] == -10                                          # he leads the slower one by 10 s
    assert G.rivals(None, attempts, 0) == []
