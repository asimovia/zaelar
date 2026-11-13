"""V2-899 — the weight log lives in the nutrition app and moves the targets; the week and the menu are built 1:1.

A weigh-in («78,4» as he types it) is a row of the body log, and the LATEST weighed row is the profile's weight
(source: every POST/PATCH/DELETE of /api/body re-read it), so the targets follow the scale. The profile takes only
valid values and an empty field goes back to the formula. The weekly evaluation and the menu coach send the model
the source's context (per-day sums + the last three evaluations; what was eaten, the targets, the margin and the
meal the hour is for) and keep nothing when there is no door. A voice `show` names the screen the card must paint.
"""
from __future__ import annotations

import pytest

from widgets import store
from widgets.nutrition import advice as act
from widgets.nutrition import data as nu


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(nu, "MODEL_DOOR", None)
    store.save("nutrition", nu._default())
    yield


def test_the_latest_weigh_in_is_the_profile_weight_and_moves_the_targets():
    nu.apply_action("set_profile", {"height_cm": 180, "age": 40, "goal": "maintain"})
    a = nu.apply_action("log_weight", {"weight_kg": "80,0", "measured_at": "2026-11-01T08:00"})
    b = nu.apply_action("log_weight", {"weight_kg": 78.4, "body_fat_pct": 17, "measured_at": "2026-11-10T08:00"})
    assert nu.load()["profile"]["weight_kg"] == 78.4 and nu.load()["profile"]["body_fat_pct"] == 17
    assert nu.view_data()["targets"]["protein_g"] == nu.jround(78.4 * 2.0)
    nu.apply_action("edit_weight", {"entry_id": a["entry_id"], "measured_at": "2026-11-12T08:00"})
    assert nu.load()["profile"]["weight_kg"] == 80.0               # the edited row is now the latest
    nu.apply_action("delete_weight", {"entry_id": a["entry_id"]})
    assert nu.load()["profile"]["weight_kg"] == 78.4
    assert nu.apply_action("restore", {"id": a["entry_id"]})["kind"] == "weight"
    assert nu.load()["profile"]["weight_kg"] == 80.0
    assert nu.apply_action("log_weight", {"weight_kg": 0})["error"] == "invalid_measure"
    assert nu.apply_action("log_weight", {"weight_kg": "abc"})["error"] == "invalid_measure"
    assert nu.apply_action("edit_weight", {"entry_id": b["entry_id"], "weight_kg": 900})["error"] == "invalid_measure"


def test_the_profile_takes_only_valid_values_and_an_empty_target_is_the_formula():
    r = nu.apply_action("set_profile", {"weight_kg": 70, "goal": "bulk", "sex": "female", "target_calories": 2300, "age": 300})
    assert r["invalid"] == ["age", "goal"] and not r["ok"]
    assert r["targets"]["calories"] == 2300 and nu.load()["profile"]["sex"] == "female"
    r = nu.apply_action("set_profile", {"target_calories": None})
    assert not r["targets"]["calories_set_by_hand"] and "target_calories" not in nu.load()["profile"]


def test_the_week_sent_to_the_model_is_the_sources_context():
    for day, kcal in (("2026-11-10", 2000), ("2026-11-11", 2500)):
        nu.apply_action("log_meal", {"description": "Lentil stew", "calories": kcal, "protein_g": 100, "eaten_at": f"{day}T14:00"})
    nu.apply_action("log_meal", {"text": "still pending", "eaten_at": "2026-11-11T21:00"})   # failed: 0 kcal, still counted as a row
    db = nu.load()
    db["evaluations"] = [{"period_start": "2026-11-01", "period_end": "2026-11-07", "score": 61, "summary": "ok",
                          "recommendations": [{"action": "more fibre"}]}]
    ctx = act.week_context(db, 7, "2026-11-13")
    assert ctx["period"] == {"start": "2026-11-06", "end": "2026-11-13", "days": 7}
    assert [(d["d"], d["kcal"], d["prot"]) for d in ctx["days"]] == [("2026-11-10", 2000, 100), ("2026-11-11", 2500, 100)]
    assert ctx["previous_evaluations"][0]["period"] == "2026-11-01..2026-11-07"
    assert ctx["target_kcal"] == nu.targets({})["calories"]          # the source hardcoded 3200 here; the profile wins
    assert nu.apply_action("evaluate_week", {})["error"] == "estimator_unavailable"
    assert nu.view_data()["evaluating"]["error"] == "estimator_unavailable" and not nu.view_data()["evaluations"]


def test_a_door_evaluation_is_normalised_and_kept(monkeypatch):
    monkeypatch.setattr(nu, "MODEL_DOOR", lambda req: {"score": "82", "summary": "steady", "strengths": ["protein", 3, None],
                        "issues": [], "recommendations": [{"action": "a"}, {"action": "b", "priority": 1}, {"why": "no action"},
                                                         {"action": "c"}, {"action": "d"}, {"action": "e"}]})
    r = nu.apply_action("evaluate_week", {"days": 99})
    e = nu.view_data()["evaluations"][0]
    assert r["ok"] and e["score"] == 82 and e["strengths"] == ["protein", "3"]
    assert [x["action"] for x in e["recommendations"]] == ["a", "b", "c", "d"] and e["recommendations"][0]["priority"] == 3
    assert nu.view_data()["view"]["screen"] == "evaluation"


def test_the_menu_coach_sees_the_day_and_the_hour(monkeypatch):
    nu.apply_action("set_profile", {"target_calories": 2400, "target_protein_g": 150})
    nu.apply_action("log_meal", {"description": "Breakfast", "calories": 600, "protein_g": 30, "eaten_at": "2026-11-13T08:30"})
    ctx = act.day_context(nu.load(), "2026-11-13T20:15:00")
    assert (ctx["meal_hint"], ctx["local_hour"], ctx["meals_count"]) == ("dinner", "20:00", 1)
    assert (ctx["remaining_kcal"], ctx["remaining_protein_g"]) == (1800, 120)
    assert [act.meal_hint(h) for h in (8, 12, 14, 17, 21, 23)] == \
        ["breakfast", "mid_morning", "lunch", "afternoon_snack", "dinner", "late_snack"]
    assert nu.apply_action("coach_menu", {"photos": []})["error"] == "no_photo"
    assert nu.apply_action("coach_menu", {"photos": ["up_nope.jpg"]})["error"] == "photo_not_found"
    p = __import__("pathlib").Path(store.data_dir("nutrition")) / "up_1_menu.jpg"
    p.write_bytes(b"x")
    assert nu.apply_action("coach_menu", {"photos": [p.name], "at": "2026-11-13T20:15"})["error"] == "estimator_unavailable"
    seen = []
    monkeypatch.setattr(nu, "MODEL_DOOR", lambda req: seen.append(req) or "**Starter** — the salad")
    assert nu.apply_action("coach_menu", {"photos": [p.name], "at": "2026-11-13T20:15", "context_text": "I ran today"})["ok"]
    assert '"remaining_kcal": 1800' in seen[0]["user"] and "I ran today" in seen[0]["user"] and len(seen[0]["images"]) == 1
    assert nu.view_data()["coach"]["recommendation"].startswith("**Starter**")


def test_show_names_the_screen_and_counts_each_order():
    nu.apply_action("show", {"screen": "weight"})
    v1 = nu.view_data()["view"]
    nu.apply_action("show", {"screen": "weight"})
    v2 = nu.view_data()["view"]
    assert v1["screen"] == v2["screen"] == "weight" and v2["n"] == v1["n"] + 1
    assert nu.apply_action("show", {"screen": "settings"})["error"] == "unknown_screen"
    m = nu.apply_action("log_meal", {"description": "Toast", "calories": 120, "eaten_at": "2026-11-12T09:00"})
    nu.apply_action("show", {"meal_id": m["meal_id"]})
    v = nu.view_data()["view"]
    assert (v["screen"], v["day"], v["meal"]) == ("today", "2026-11-12", m["meal_id"])
    now = nu.apply_action("log_meal", {"description": "Lentil stew", "calories": 500})        # eaten now
    refs = {r["id"]: r for r in nu.ref_index()}
    assert refs[now["meal_id"]]["field"] == "meal_id" and refs[now["meal_id"]]["label"] == "Lentil stew"
