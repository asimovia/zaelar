"""V2-901 — a ride's stats and 1-km splits, ported 1:1 from the source app, on synthetic tracks.

Moving time counts only what goes over 2 km/h (a stop at a light is not riding); a gap over ten minutes between two
fixes is left out of everything; the climb is measured on a 5-point median of the altitude, so one GPS spike is
not a hill; a split closes every km with its time, speed, climb and mean heart rate.
"""
from __future__ import annotations

from tests.browser.unit.cycling.conftest import straight_track
from widgets.cycling import engine as E


def _shift(points, seconds):
    return [dict(p, ts=E.iso(E.ts_ms(p["ts"]) + seconds * 1000)) for p in points]


def test_moving_time_leaves_out_the_stop_and_the_long_gap():
    ride = straight_track(41, 6.0, every_s=5, hr=120)                    # 200 s riding, 1.2 km
    stop = [dict(ride[-1], ts=E.iso(E.ts_ms(ride[-1]["ts"]) + i * 5000)) for i in range(1, 13)]   # 60 s stopped
    tail = _shift(straight_track(21, 6.0, lat0=ride[-1]["lat"], every_s=5, hr=120), 260)[1:]
    after_gap = _shift(tail, 900)                                       # 15 minutes without a fix: dropped
    st = E.compute_session_stats(ride + stop + tail + after_gap)
    assert st["moving_time_sec"] == 200 + 100 + 95, st                  # the stop and the 15-min gap do not count
    assert st["duration_sec"] == E.jround((E.ts_ms(after_gap[-1]["ts"]) - E.ts_ms(ride[0]["ts"])) / 1000)
    assert abs(st["avg_speed_kmh"] - 21.6) < 0.2 and st["max_speed_kmh"] < 22
    assert st["avg_hr"] is not None and st["max_hr"] == 126


def test_one_altitude_spike_is_not_a_climb():
    tr = straight_track(30, 6.0, every_s=5, alt0=200.0)
    tr[12] = dict(tr[12], altitude_m=260.0)                             # a GPS altitude spike
    st = E.compute_session_stats(tr)
    assert st["elevation_gain_m"] == 0 and st["elevation_loss_m"] == 0, st
    up = straight_track(30, 6.0, every_s=5, alt0=200.0, climb_per_pt=1.0)
    # 29 m ridden; the 5-point median shaves a metre at each end (its window shrinks there) — the source's figure.
    assert E.compute_session_stats(up)["elevation_gain_m"] == 27


def test_a_split_closes_every_km_with_its_figures():
    tr = straight_track(100, 5.0, every_s=5, hr=140, climb_per_pt=0.5)  # 25 m per point: a km every ~40 points
    sp = E.compute_session_splits(tr, 1)
    assert [s["idx"] for s in sp] == [1, 2], sp
    s1 = sp[0]
    assert s1["distance_km"] >= 1 and s1["duration_sec"] in (200, 205)    # it closes on the first fix past the km
    assert s1["avg_speed_kmh"] == 18.0                                   # 25 m every 5 s, whatever the split's length
    assert s1["elevation_gain_m"] == E.jround(s1["duration_sec"] / 5 * 0.5) and s1["avg_hr"] is not None
    assert sp[1]["duration_sec"] in (200, 205) and abs(sp[1]["avg_speed_kmh"] - 18.0) < 0.6
    assert E.compute_session_splits(tr[:1]) == [] and E.compute_session_stats(tr[:1]) is None
