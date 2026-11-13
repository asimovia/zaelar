"""V2-901 — segments through the app's actions: made from a saved ride, ranked over every earlier ride, raced again.

A segment said in kilometres along a ride lands on the real path between them; creating it ranks every saved ride;
a faster ride takes the PR when it is saved; deleting the ride that held the PR gives the PR back to the next best
(the source left a deleted ride's time standing); renaming, recalculating and deleting work by the name he says.
"""
from __future__ import annotations

import pytest

from tests.browser.unit.cycling.conftest import straight_track
from widgets.cycling import tracks
from widgets.cycling import segments as SG


def _saved(cyc, track, name=None):
    """A ride saved straight into the store, the way `stop` leaves one."""
    db = cyc._load()
    rid = SG._next_id(db, "session")
    db["sessions"].append({"id": rid, "status": "done", "started_at": track[0]["ts"], "name": name,
                           "distance_km": 2.0, "duration_sec": 400, "start_lat": track[0]["lat"],
                           "start_lng": track[0]["lng"], "locality": None, "weather_temp_c": None})
    cyc._save(db)
    tracks.append(rid, track)
    return rid


@pytest.fixture
def three(cyc):
    t = [straight_track(80, 6.0, t0=1_700_000_000_000 + k * 86_400_000, slow=slow, hr=130)
         for k, slow in enumerate([None, (10, 50, 0.7), None])]
    return [_saved(cyc, t[0], "Monday"), _saved(cyc, t[1], "Tuesday"), t[2]]


def test_a_segment_said_in_km_ranks_every_saved_ride(cyc, three):
    r = cyc.apply_action("create_segment", {"ride": "Monday", "name": "The climb", "from_km": 0.3, "to_km": 1.5})
    assert r["ok"] and 1150 <= r["distance_m"] <= 1250, r
    assert r["passes"] == 2 and r["ranking"][0]["time_sec"] < r["ranking"][1]["time_sec"]
    seg = cyc.view_data()["segments"][0]
    assert seg["name"] == "The climb" and seg["attempts"] == 2 and seg["pr_time_sec"] == r["ranking"][0]["time_sec"]
    assert cyc.view_data()["ui"]["view"] == "segment"
    assert not cyc.apply_action("create_segment", {"ride": "Monday", "from_km": 0.3, "to_km": 1.5})["ok"]   # needs a name
    assert not cyc.apply_action("create_segment", {"ride": "Monday", "name": "x", "from_km": 1, "to_km": 1})["ok"]


def test_a_faster_ride_takes_the_pr_and_deleting_it_gives_it_back(cyc, three):
    cyc.apply_action("create_segment", {"ride": "Monday", "name": "The climb", "from_km": 0.3, "to_km": 1.5})
    old_pr = cyc.view_data()["segments"][0]["pr_time_sec"]
    fast = [dict(p) for p in straight_track(80, 8.0, t0=1_700_300_000_000)]
    rid = _saved(cyc, fast, "Fast")
    db = cyc._load()
    res = SG.process_session_segments(db, rid, tracks.load)                   # what `stop` runs on a saved ride
    cyc._save(db)
    assert res["passes"][0]["isPr"] and cyc.view_data()["segments"][0]["pr_time_sec"] < old_pr
    det = cyc.apply_action("ride_detail", {"ride": "Fast"})
    assert det["ok"] and det["attempts"][0]["is_pr"] == 1 and det["stats"]["trackpoint_count"] == 80
    assert cyc.apply_action("delete_ride", {"ride": "Fast"})["ok"]
    seg = cyc.view_data()["segments"][0]
    assert seg["pr_time_sec"] == old_pr and seg["attempts"] == 2              # the PR goes back to a ride that exists


def test_rename_recalc_and_delete_by_the_name_he_says(cyc, three):
    cyc.apply_action("create_segment", {"ride": "last", "name": "The climb", "from_km": 0.3, "to_km": 1.5})
    assert cyc.apply_action("rename_segment", {"segment": "the climb", "name": "Hill"})["name"] == "Hill"
    r = cyc.apply_action("recalc_segment", {"segment": "hill"})
    assert r["ok"] and r["passes"] == 2
    d = cyc.apply_action("segment_detail", {"segment": "Hill"})
    assert d["ok"] and len(d["top3"]) == 2 and d["pr_speed_kmh"] and len(d["polyline"]) >= 2
    labels = {(x["field"], x["label"]) for x in cyc.ref_index()}
    assert ("segment", "Hill") in labels and any(f == "ride" and "Monday" in lab for f, lab in labels)
    assert cyc.apply_action("delete_segment", {"segment": "Hill"})["ok"]
    assert cyc.view_data()["segments"] == [] and cyc._load()["attempts"] == []
    assert cyc.apply_action("rename_segment", {"segment": "nope", "name": "x"})["error"] == "segment_not_found"
