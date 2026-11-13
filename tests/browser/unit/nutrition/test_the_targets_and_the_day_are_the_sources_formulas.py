"""V2-899 — the nutrition app's numbers are the source PWA's, ported 1:1, and a day is read the way it read it.

Daily targets: Mifflin-St Jeor BMR x 1.55, x (1 ± surplus) by goal, protein g/kg, a fixed target wins; the logical day
starts at 03:00; the day's quality is the kcal-weighted mean of the 1-5 scores and its light needs lunch AND dinner;
the 0-100 day score is protein 35 + variety 40 + kcal balance 25 (capped under 600 kcal). One deliberate change from
the source: the variety words are WHOLE words (its substring table read «agua», water, inside «aguacate», avocado).
"""
from __future__ import annotations

import pytest

from widgets.nutrition import data as nu


def _meal(when, kcal, prot=0, score=None, desc="", status="done", tags=None):
    m = {"eaten_at": when, "calories": kcal, "protein_g": prot, "health_score": score, "description": desc, "status": status}
    if tags is not None:
        m["estimate"] = {"components": tags}
    return m


def test_targets_are_the_source_formula_and_a_fixed_target_wins():
    # source: tdee = round((10w + 6.25h - 5age + 5) * 1.55); gain x 1.15; protein = w * 2.0
    t = nu.targets({"weight_kg": 80, "height_cm": 180, "age": 40, "goal": "gain"})
    tdee = round((10 * 80 + 6.25 * 180 - 5 * 40 + 5) * 1.55)
    assert (t["tdee"], t["calories"], t["protein_g"], t["tdee_source"]) == (tdee, round(tdee * 1.15), 160, "formula")
    assert nu.targets({"weight_kg": 80, "height_cm": 180, "age": 40, "goal": "lose", "surplus_pct": 20})["calories"] == round(tdee * 0.8)
    assert nu.targets({"weight_kg": 80, "height_cm": 180, "age": 40, "goal": "maintain"})["calories"] == tdee
    # an empty profile gives the source's defaults (75 kg, 175 cm, 30 y, gain, 15 %, 2.0 g/kg)
    d = nu.targets({})
    assert d["calories"] == round(round((750 + 6.25 * 175 - 150 + 5) * 1.55) * 1.15) and d["protein_g"] == 150
    fixed = nu.targets({"weight_kg": 80, "target_calories": 2500, "target_protein_g": 170})
    assert (fixed["calories"], fixed["protein_g"], fixed["calories_set_by_hand"]) == (2500, 170, True)
    # the one addition: female uses -161; unknown keeps the source's +5
    assert nu.targets({"weight_kg": 60, "height_cm": 165, "age": 30, "sex": "female", "goal": "maintain"})["tdee"] == \
        round((600 + 6.25 * 165 - 150 - 161) * 1.55)
    # three or more measured burn days replace the formula (source realAvgBurn)
    assert nu.targets({"goal": "maintain"}, burned_days=[2400, 2600, 2500])["tdee"] == 2500
    assert nu.targets({"goal": "maintain"}, burned_days=[2400, 2600])["tdee_source"] == "formula"


def test_the_day_starts_at_three_and_the_goal_band_is_five_percent():
    assert nu.logical_day("2026-11-13T02:30") == "2026-11-12"
    assert nu.logical_day("2026-11-13 03:00:00") == "2026-11-13"
    assert nu.logical_day("not a date") is None
    assert nu.goal_status(2000, 2000) == "on" and nu.goal_status(2079, 2000) == "on"
    assert nu.goal_status(2200, 2000) == "over" and nu.goal_status(1500, 2000) == "low"
    assert nu.goal_status(3050, 3000) == "on"          # ±5 % of 3000 = 150 > 80


def test_quality_is_kcal_weighted_and_the_light_needs_lunch_and_dinner():
    day = [_meal("2026-11-13T09:00", 100, score=1), _meal("2026-11-13T14:00", 900, score=5)]
    assert nu.health_avg(day) == pytest.approx((100 * 1 + 900 * 5) / 1000)
    assert nu.jround(2.5) == 3 and nu.jround(14.5) == 15 and nu.jround(-0.5) == 0      # Math.round, not round()
    assert nu.day_rating(day)["rating"] == "gray"              # no dinner yet: incomplete, never a verdict
    day.append(_meal("2026-11-13T21:00", 600, score=3))
    r = nu.day_rating(day)
    assert r["has_main_meals"] and r["rating"] == "green"      # (100+4500+1800)/1600 = 4.0
    day.append(_meal("2026-11-13T22:00", 800, score=1))
    assert nu.day_rating(day)["rating"] == "yellow"
    assert nu.day_rating([_meal("2026-11-13T14:00", 500, status="pending", score=1),
                          _meal("2026-11-13T21:00", 500, score=5)])["has_main_meals"] is False


def test_the_day_score_is_protein_variety_and_balance():
    tgt = {"calories": 2000, "protein_g": 100}
    full = [_meal("2026-11-13T14:00", 1900, prot=100, tags=["veg", "leg", "prot", "fruit", "grain", "fat", "water"])]
    assert nu.day_score(full, tgt) == 100
    half = [_meal("2026-11-13T14:00", 1500, prot=50, tags=["veg", "prot"])]        # 0.75 → 17 kcal points
    assert nu.day_score(half, tgt) == round(17.5 + 2 / 7 * 40 + 17)
    morning = [_meal("2026-11-13T09:00", 500, prot=30, tags=[])]
    assert nu.day_score(morning, tgt) == 15        # 10.5 + 0 + 4 = 14.5 → 15, as JavaScript's Math.round gives it
    assert nu.day_score([], tgt) is None


def test_variety_words_are_whole_words_and_the_models_tags_win():
    assert "water" not in nu.components([_meal("x", 300, desc="Salmón con aguacate")])
    assert {"prot", "fat"} <= set(nu.components([_meal("x", 300, desc="Salmón con aguacate")]))
    assert "water" in nu.components([_meal("x", 1, desc="un vaso de agua")])
    assert "leg" in nu.components([_meal("x", 300, desc="Lentejas estofadas")])        # a stem
    assert "veg" in nu.components([_meal("x", 300, desc="Grilled chicken with tomatoes")])
    assert nu.components([_meal("x", 300, desc="Salmón", tags=["fruit"])]) == ["fruit"]
