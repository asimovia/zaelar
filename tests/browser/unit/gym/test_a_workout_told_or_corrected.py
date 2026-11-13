"""V2-900 — a workout done elsewhere and a recorded one corrected. The agent fills the structure itself (`log_workout`
with exercises and sets, `edit_session` with the original PWA's six operations on E1/E1.1); a sentence goes through the widget's
ONE model seam, which today answers «not available» with the way to say it — and nothing is written. Invalid
operations touch nothing. The seam is the only door to a model: no module of the widget reaches the network.
"""
from __future__ import annotations

import re
from pathlib import Path

from widgets.gym import coach
from widgets.gym import data as g


def test_a_workout_is_logged_from_its_structure_both_shapes():
    r = g.apply_action("log_workout", {"date": "2026-11-10", "day_key": "legs", "exercises": [
        {"name": "Goblet squat", "sets": 3, "reps": 12, "weight_kg": 20},
        {"name": "Prensa inclinada", "sets": [{"reps": 12, "weight_kg": 100}, {"reps": 10, "weight_kg": 110}]}]})
    assert r["ok"] and r["sets"] == 5
    s = g.view_data()["sessions"][0]
    assert (s["date"], s["day_key"], s["status"], s["source"]) == ("2026-11-10", "legs", "done", "manual")
    assert [e["key"] for e in s["exercises"]] == ["goblet-squat", "leg-press"]      # a Spanish name finds its key
    assert s["volume_kg"] == 3 * 12 * 20 + 1200 + 1100


def test_a_sentence_needs_the_seam_and_nothing_is_written_without_it():
    r = g.apply_action("log_workout", {"text": "yesterday 4x10 bench at 20"})
    assert r["error"] == "model_unavailable" and "exercises" in r["hint"]
    r = g.apply_action("edit_session", {"sessionId": "1", "instruction": "x"})
    assert r["error"] == "session_not_found"
    assert g.apply_action("adjust_today", {"instruction": "30 minutes"})["error"] == "model_unavailable"
    assert g.apply_action("refresh_plan", {})["error"] == "model_unavailable"
    assert g._load()["sessions"] == []


def _logged():
    g.apply_action("log_workout", {"date": "2026-11-10", "exercises": [
        {"name": "Dumbbell bench press", "sets": 2, "reps": 10, "weight_kg": 20},
        {"name": "Lat pulldown", "sets": 1, "reps": 10, "weight_kg": 50}]})
    return str(g.view_data()["sessions"][0]["id"])


def test_the_six_operations_correct_a_recorded_workout():
    sid = _logged()
    r = g.apply_action("edit_session", {"sessionId": sid, "ops": [
        {"op": "edit_set", "exercise_index": 1, "set_index": 1, "weight_kg": 22.5},
        {"op": "add_set", "exercise_index": 2},
        {"op": "replace_exercise", "exercise_index": 2, "name": "Seated cable row", "sets": [{"reps": 12, "weight_kg": 45}]},
        {"op": "add_exercise", "name": "Plank", "sets": [{"reps": 1}]}]})
    assert r["ok"] and r["applied"] == 4
    ex = g.view_data()["sessions"][0]["exercises"]
    assert [(e["label"], e["key"]) for e in ex] == [("E1", "db-bench"), ("E2", "seated-row"), ("E3", "plank")]
    assert [x["weight_kg"] for x in ex[0]["sets"]] == [20, 22.5]
    assert [(x["reps"], x["weight_kg"]) for x in ex[1]["sets"]] == [(12, 45)]


def test_operations_that_name_nothing_touch_nothing():
    sid = _logged()
    before = g._load()["sets"]
    r = g.apply_action("edit_session", {"sessionId": sid, "ops": [{"op": "edit_set", "exercise_index": 9, "set_index": 0},
                                                                 {"op": "delete_set", "exercise_index": 1, "set_index": 7},
                                                                 {"op": "fly", "exercise_index": 1}]})
    assert r["error"] == "no_valid_ops" and g._load()["sets"] == before


def test_deleting_a_workout_or_a_day_never_touches_the_live_session():
    sid = _logged()
    g.apply_action("select_program", {"program": "functional-hypertrophy"})
    g.apply_action("start_session", {})
    live = g.view_data()["live"]["session_id"]
    assert g.apply_action("delete_session", {"sessionId": str(live)})["error"] == "session_is_live"
    assert g.apply_action("delete_day", {"date": g._today()})["deleted"] == 0
    assert g.apply_action("delete_session", {"sessionId": sid})["ok"]
    assert [s["id"] for s in g._load()["sessions"]] == [live]


def test_the_seam_is_the_only_door_to_a_model():
    assert coach.available() is False
    for kind in coach.KINDS:
        assert coach.ask(kind, {}) == {"ok": False, "error": "model_unavailable"}
        assert coach.render(kind, {"language": "English"})["system"]          # every prompt ships as data
    prompts = Path(coach.__file__).with_name("prompts.json").read_text(encoding="utf-8")
    assert "Mass Functional" not in prompts and "entrenador personal de" not in prompts   # no persona, no program name
    src = "".join(p.read_text(encoding="utf-8") for p in Path(coach.__file__).parent.glob("*.py"))
    assert not re.search(r"\b(urllib|http\.client|requests|httpx|socket)\b", src)
