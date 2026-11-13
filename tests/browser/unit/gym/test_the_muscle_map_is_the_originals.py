"""V2-900 — the muscle recovery map is the original PWA's `muscle-state.js`, number for number: primary sets count 1, secondary
0.5; building −5…+5 by days since and sets in 7 days; opportunity −5 (just trained) … 0 (the window) … +5 (never or
12+ days); 21-day horizon; a name the map lacks is inferred from its words (ES and EN); an alternative credits the
program exercise it stood in for. The widget's colours follow the same thresholds and never say a state by colour alone.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from widgets.gym import muscles as m

NOW = 1_800_000_000.0
DAY = 86400


def _state(sets):
    return {x["muscle"]: x for x in m.compute_muscle_state(sets, NOW)}


def _set(key, days_ago, name=None, muscle_key=None, reps=10, w=20):
    return {"exercise_key": key, "exercise_name": name, "muscle_key": muscle_key, "completed_at": NOW - days_ago * DAY,
            "reps_done": reps, "weight_kg": w}


def test_never_trained_is_no_data_and_losing():
    s = _state([])
    assert (s["chest"]["opportunity_score"], s["chest"]["opportunity_state"]) == (5, "no_data")
    assert (s["chest"]["building_score"], s["chest"]["building_state"]) == (-5, "losing")
    assert s["chest"]["days_since"] is None and len(s) == 11


@pytest.mark.parametrize("days,opp,state", [(0.5, -5, "fatigued"), (1.5, -3, "recovering"), (3, 0, "optimal"),
                                             (5, 1, "window_closing"), (8, 3, "train_soon"), (10, 4, "urgent"),
                                             (13, 5, "critical")])
def test_the_opportunity_window_by_days_since(days, opp, state):
    s = _state([_set("db-bench", days)])["chest"]
    assert (s["opportunity_score"], s["opportunity_state"]) == (opp, state)


def test_building_counts_primary_one_and_secondary_half():
    sets = [_set("db-bench", 1) for _ in range(4)]          # chest primary ×4, triceps + shoulders secondary ×4
    s = _state(sets)
    assert s["chest"]["sets_7d"] == 4 and s["triceps"]["sets_7d"] == 2
    assert (s["chest"]["building_score"], s["chest"]["building_state"]) == (2, "growing")
    assert (s["triceps"]["building_score"], s["triceps"]["building_state"]) == (1, "touched")
    ten = _state([_set("db-bench", 1) for _ in range(10)])["chest"]
    assert (ten["building_score"], ten["building_state"]) == (5, "building")


def test_old_work_falls_and_the_horizon_is_21_days():
    assert _state([_set("db-bench", 9)])["chest"]["building_state"] == "standby"
    assert _state([_set("db-bench", 11)])["chest"]["building_score"] == -3
    assert _state([_set("db-bench", 22)])["chest"]["opportunity_state"] == "no_data"


def test_a_name_the_map_lacks_is_inferred_in_both_languages():
    assert _state([_set("x", 1, name="Sentadilla búlgara")])["quads"]["sets_7d"] == 1
    assert _state([_set("x", 1, name="Hammer curl")])["biceps"]["sets_7d"] == 1
    assert _state([_set("x", 1, name="Something else")])["chest"]["days_since"] is None


def test_an_alternative_credits_the_exercise_it_stood_in_for():
    s = _state([_set("machine-chest", 1, name="Machine chest press", muscle_key="db-bench")])
    assert s["chest"]["sets_7d"] == 1 and s["shoulders"]["sets_7d"] == 0.5     # db-bench's secondaries, not machine-chest's


def test_the_card_colours_follow_the_same_thresholds():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required")
    script = Path(__file__).with_name("test_the_card_paints_every_screen.mjs")
    r = subprocess.run([node, str(script), "colours"], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr
