"""V2-900 — the guided session is the original PWA's, and it lives in the widget's store so every screen and the voice drive the
same one: a timed block runs its timer and «next» leaves it; a set is saved with what is on screen (the LAST real
weight of that exercise first, the program's suggestion otherwise) and starts the rest; a timer that ran out is
counted once and only against the cursor the screen saw; a rest that ends with the heart above 130 gets 30 s more,
once; undo goes back to that set; skip records it; the end advances the rotation; abort leaves nothing.
"""
from __future__ import annotations

import time

from widgets.gym import data as g


def _start():
    assert g.apply_action("select_program", {"program": "functional-hypertrophy"})["ok"]
    assert g.apply_action("start_session", {})["ok"]
    return g.view_data()["live"]


def _to_first_exercise():
    lv = g.view_data()["live"]
    while lv["block"]["type"] != "exercise":
        g.apply_action("next", {})
        lv = g.view_data()["live"]
    return lv


def _expire_timer():
    db = g._load()
    db["live"]["timer"]["ends_at"] = int((time.time() - 1) * 1000)
    g._save(db)


def test_a_timed_block_runs_its_timer_and_next_leaves_it():
    lv = _start()
    assert lv["block"]["type"] == "stretch" and lv["timer"]["left"] == 120 and not lv["timer"]["paused"]
    assert g.apply_action("set_done", {})["error"] == "not_an_exercise"
    assert g.apply_action("next", {})["block"] == 1


def test_a_set_saves_what_is_on_screen_and_starts_the_rest():
    _start()
    lv = _to_first_exercise()
    assert (lv["block"]["key"], lv["weight"], lv["reps"]) == ("db-bench", 18, 10)     # the program's suggestion
    g.apply_action("set_values", {"weight_delta": 2.5})
    r = g.apply_action("set_done", {"reps": 9})
    assert r["saved"] == {"set": 1, "of": 4, "reps": 9, "weight_kg": 20.5} and r["resting"]
    lv = g.view_data()["live"]
    assert lv["resting"] and lv["timer"]["total"] == 90 and lv["set"] == 1
    assert g.apply_action("set_done", {})["error"] == "resting"


def test_the_last_real_weight_wins_over_the_suggestion_next_time():
    _start()
    _to_first_exercise()
    g.apply_action("set_done", {"weight_kg": 24})
    g.apply_action("finish", {})
    g.apply_action("start_session", {"day": "push"})
    lv = _to_first_exercise()
    assert lv["weight"] == 24 and lv["last_weight"] == 24


def test_a_timer_that_ran_out_counts_once_and_only_for_the_cursor_it_saw():
    _start()
    seen = {"i": 0, "set": 0, "resting": False}
    assert g.apply_action("timer_done", seen).get("ignored")                    # not run out yet
    _expire_timer()
    assert g.apply_action("timer_done", {"i": 0, "set": 0, "resting": True}).get("ignored")   # another cursor
    assert g.apply_action("timer_done", seen)["block"] == 1
    assert g.apply_action("timer_done", seen).get("ignored")                    # the second screen's report


def test_a_rest_that_ends_with_the_heart_high_gets_thirty_seconds_once():
    _start()
    _to_first_exercise()
    g.apply_action("claim", {"owner": "phone"})
    assert g.apply_action("hr", {"owner": "laptop", "bpm": 150}).get("owned_by_another_screen")
    g.apply_action("set_done", {})
    g.apply_action("hr", {"owner": "phone", "bpm": 142})
    _expire_timer()
    cur = {"i": 3, "set": 1, "resting": True}
    g.apply_action("timer_done", cur)
    lv = g.view_data()["live"]
    assert lv["resting"] and lv["timer"]["total"] == 30 and lv["note"]["bpm"] == 142
    _expire_timer()
    g.apply_action("timer_done", cur)
    lv = g.view_data()["live"]
    assert not lv["resting"] and lv["timer"] is None and lv["cue_kind"] == "end"


def test_undo_goes_back_to_that_set_and_skip_is_recorded():
    _start()
    _to_first_exercise()
    g.apply_action("set_done", {"reps": 10, "weight_kg": 18})
    g.apply_action("next", {})
    g.apply_action("set_done", {"reps": 8, "weight_kg": 20})
    assert g.apply_action("undo_set", {})["undone"]["reps"] == 8
    lv = g.view_data()["live"]
    assert (lv["i"], lv["set"], lv["sets_count"], lv["weight"]) == (3, 1, 1, 20)
    r = g.apply_action("skip_exercise", {})
    assert r["skipped"] == "Dumbbell bench press" and g.view_data()["live"]["i"] == 4
    assert g._load()["events"][-1]["type"] == "skipped"


def test_the_end_advances_the_rotation_and_abort_leaves_nothing():
    _start()
    _to_first_exercise()
    g.apply_action("set_done", {})
    assert g.apply_action("end_early", {})["status"] == "partial"
    v = g.view_data()
    assert v["status"] == "ready" and v["next"]["day_key"] == "legs" and v["next"]["last"] == "push"
    assert v["sessions"][0]["status"] == "partial" and v["program"]["day_index"] == 1
    g.apply_action("start_session", {})
    _to_first_exercise()
    g.apply_action("set_done", {})
    assert g.apply_action("abort", {})["ok"]
    v = g.view_data()
    assert v["status"] == "ready" and len(v["sessions"]) == 1 and v["next"]["day_key"] == "legs"


def test_a_session_resumes_instead_of_starting_twice():
    _start()
    assert g.apply_action("start_session", {}).get("resumed")
    assert len(g._load()["sessions"]) == 1


def test_an_alternative_from_the_list_replaces_the_block_and_keeps_its_muscles():
    _start()
    _to_first_exercise()
    first = g.apply_action("suggest_alternative", {})["alternative"]
    second = g.apply_action("suggest_alternative", {})["alternative"]
    assert first == "Barbell bench press" and second == "Machine chest press"
    assert g.view_data()["live"]["alt"]["rejected"] == ["Barbell bench press"]
    g.apply_action("use_alternative", {})
    b = g.view_data()["live"]["block"]
    assert b["key"] == "machine-chest" and b["muscle_key"] == "db-bench" and b["type"] == "exercise"
    g.apply_action("set_done", {})
    assert g._load()["sets"][-1]["muscle_key"] == "db-bench"
    assert g._load()["events"][-1]["type"] == "alternative"


def test_a_list_exhausted_asks_the_seam_and_says_so():
    _start()
    _to_first_exercise()
    for _ in range(3):
        r = g.apply_action("suggest_alternative", {})
    assert r["alternative"] is None and r["exhausted"]
    assert g.view_data()["live"]["alt"]["model"] is False
