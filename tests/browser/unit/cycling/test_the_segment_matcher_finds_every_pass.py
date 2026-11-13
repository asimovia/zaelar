"""V2-901 — the segment matcher, ported 1:1: every pass of a segment inside a ride, on synthetic GPS tracks.

The approach to a segment's start and end is measured PERPENDICULAR to the route line, so a track sampled every
5 s (≈30 m between fixes) still meets a 25 m tolerance; a ride that crosses the segment twice yields two passes; a
ride the wrong way yields none; the mean speed uses the segment's canonical distance (a better time is always a
better mean); and the rounding is JavaScript's half-up, never Python's half-to-even.
"""
from __future__ import annotations

from tests.browser.unit.cycling.conftest import M_PER_DEG_LAT, straight_track
from widgets.cycling import engine as E
from widgets.cycling import segments as SG


def _seg(track, i0, i1, distance_m=None):
    a, b = track[i0], track[i1]
    return {"id": 1, "start_lat": a["lat"], "start_lng": a["lng"], "end_lat": b["lat"], "end_lng": b["lng"],
            "distance_m": distance_m}


def test_a_sparse_track_still_meets_the_segment_ends():
    tr = straight_track(120, speed_mps=6.0, every_s=10, hr=130)         # 60 m between fixes
    seg = _seg(tr, 20, 60)
    # Move the segment's ends to the MIDDLE between two fixes: 30 m from the nearest vertex on each side — beyond
    # the 25 m tolerance, so only the perpendicular measure to the route line can meet them.
    half = 30 / M_PER_DEG_LAT
    seg["start_lat"] += half
    seg["end_lat"] += half
    passes = E.find_segment_passes(tr, seg)
    assert len(passes) == 1, passes
    p = passes[0]
    assert p["time_sec"] == 400 and 2390 <= p["distance_m"] <= 2410, p
    assert p["avg_hr"] is not None and p["max_hr"] >= p["avg_hr"]


def test_two_crossings_are_two_passes_and_the_wrong_way_is_none():
    out = straight_track(60, every_s=5)
    back = [dict(p, ts=E.iso(E.ts_ms(out[-1]["ts"]) + (i + 1) * 5000)) for i, p in enumerate(reversed(out))]
    loop = out + back + [dict(p, ts=E.iso(E.ts_ms(back[-1]["ts"]) + (i + 1) * 5000)) for i, p in enumerate(out)]
    seg = _seg(out, 10, 40)
    assert len(E.find_segment_passes(loop, seg)) == 2           # out and the second out; never the way back
    assert E.find_segment_passes(back, seg) == []


def test_the_mean_uses_the_canonical_distance_and_rounds_half_up():
    tr = straight_track(80, speed_mps=5.0, every_s=5)
    seg = _seg(tr, 10, 50, distance_m=1000)
    p = E.find_segment_passes(tr, seg)[0]
    assert p["time_sec"] == 200
    assert p["avg_speed_kmh"] == 18.0                              # 1000 m in 200 s, NOT the measured ~1000 m
    assert E.jround(2.5) == 3 and E.jround(-2.5) == -2 and E.jround(0.125, 2) == 0.13   # Math.round, not round()


def test_backfill_ranks_every_ride_and_the_pr_is_the_best_time():
    db = {"sessions": [], "segments": [], "attempts": [], "next_id": {}}
    tracks = {1: straight_track(80, 6.0, every_s=5), 2: straight_track(80, 6.0, every_s=5, slow=(15, 45, 0.7)),
              3: straight_track(80, 7.0, every_s=5)}
    for sid in tracks:
        db["sessions"].append({"id": sid, "status": "done", "started_at": E.iso(1e12 + sid * 86400000)})
    db["segments"].append(_seg(tracks[1], 10, 40, distance_m=900))
    res = SG.backfill_segment_attempts(db, 1, lambda sid: tracks[sid])
    times = [r["time_sec"] for r in res["ranking"]]
    assert times == sorted(times) and len(times) == 3
    assert res["segment"]["pr_time_sec"] == times[0] and res["segment"]["attempts"] == 3
    again = SG.backfill_segment_attempts(db, 1, lambda sid: tracks[sid])     # idempotent: from scratch every time
    assert [r["time_sec"] for r in again["ranking"]] == times and len(db["attempts"]) == 3
