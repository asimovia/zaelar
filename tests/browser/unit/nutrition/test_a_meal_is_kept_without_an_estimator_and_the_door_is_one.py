"""V2-899 — a meal is never lost for want of a model, and every model call goes through ONE door.

There is no model seam for apps yet (phase I wires it), so `estimate()` answers `estimator_unavailable`: a meal said
in words is SAVED as failed-with-a-reason and stays editable by hand (a correction makes it done). With a door, the
same meal is estimated with the source's prompt; the answer is clamped the source's way (score 1-5, no 0-kcal photo
of a non-food), a refinement appends to the words and estimates again, and a time change alone does not. A photo is
a FILE the card uploaded into the app's data dir — the store keeps its name, never its bytes.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from widgets import store
from widgets.nutrition import data as nu

APP = Path(nu.__file__).resolve().parent


@pytest.fixture(autouse=True)
def _no_door(monkeypatch):
    monkeypatch.setattr(nu, "MODEL_DOOR", None)
    store.save("nutrition", nu._default())
    yield


def _photo(name="up_0123abcd_meal.jpg") -> str:
    p = Path(store.data_dir("nutrition")) / name
    p.write_bytes(b"\xff\xd8\xff fake jpeg")
    return name


def test_without_a_door_the_meal_is_saved_with_its_reason_and_fixed_by_hand():
    r = nu.apply_action("log_meal", {"text": "two eggs and wholegrain toast", "eaten_at": "2026-11-13T09:10"})
    assert r["ok"] and r["status"] == "failed" and r["reason"] == "estimator_unavailable"
    m = nu.load()["meals"][0]
    assert m["source_text"] == "two eggs and wholegrain toast" and m["eaten_at"] == "2026-11-13T09:10:00"
    assert nu.apply_action("retry_meal", {"meal_id": r["meal_id"]})["error"] == "estimator_unavailable"
    e = nu.apply_action("edit_meal", {"meal_id": r["meal_id"], "calories": "310", "protein_g": 19, "description": "Eggs on toast"})
    assert e["status"] == "done"
    v = nu.view_data()
    meal = next(x for x in v["meals"] if x["id"] == r["meal_id"])
    assert (meal["status"], meal["calories"], meal["error"]) == ("done", 310.0, None)
    assert not v["estimator"]["available"] and "entered by hand" in nu.prompt_digest()
    # numbers he gives are a done meal straight away, no estimate asked
    assert nu.apply_action("log_meal", {"text": "a banana", "calories": 105})["status"] == "done"


def test_with_a_door_the_meal_is_estimated_with_the_sources_prompt(monkeypatch):
    seen = []

    def door(req):
        seen.append(req)
        return {"description": "Eggs on toast", "totals": {"calories": 320, "protein_g": 18, "carbs_g": 22, "fat_g": 16,
                "fiber_g": 4, "grams": 210}, "health_score": 9, "health_reason": "whole food" * 20,
                "ingredients": [{"item": "egg", "grams": 100, "kcal": 150}], "components": ["prot", "grain", "nope"],
                "confidence": 0.8, "notes": "assumed fried"}
    monkeypatch.setattr(nu, "MODEL_DOOR", door)
    name = _photo()
    r = nu.apply_action("log_meal", {"photo": name, "text": "fried in olive oil", "lang": "es"})
    assert r["status"] == "done"
    req = seen[-1]
    assert req["kind"] == "meal" and "health_score" in req["system"] and "«es»" in req["system"]
    assert "fried in olive oil" in req["user"] and req["images"] == [str(Path(store.data_dir("nutrition")) / name)]
    m = nu.load()["meals"][0]
    assert m["health_score"] == 5 and len(m["health_reason"]) == 100 and m["estimate"]["components"] == ["prot", "grain", "nope"]
    assert nu.components([m]) == ["prot", "grain"]           # an unknown tag counts for nothing
    # refine appends his words and estimates again; a time change alone does not
    nu.apply_action("refine_meal", {"meal_id": r["meal_id"], "text": "I only ate half"})
    assert "[Refinement from the person]: I only ate half" in seen[-1]["user"] and len(seen) == 2
    nu.apply_action("refine_meal", {"meal_id": r["meal_id"], "eaten_at": "2026-11-13T15:00"})
    assert len(seen) == 2 and nu.load()["meals"][0]["eaten_at"] == "2026-11-13T15:00:00"


def test_a_photo_with_no_food_fails_and_a_broken_door_is_a_failed_estimate(monkeypatch):
    monkeypatch.setattr(nu, "MODEL_DOOR", lambda req: {"totals": {"calories": 0}, "confidence": 0.1, "notes": "not food"})
    r = nu.apply_action("log_meal", {"photo": _photo()})
    assert r["status"] == "failed" and r["reason"] == "no_food_identified"

    def boom(req):
        raise RuntimeError("provider down")
    monkeypatch.setattr(nu, "MODEL_DOOR", boom)
    r = nu.apply_action("log_meal", {"text": "a salad"})
    assert r["ok"] and r["status"] == "failed" and r["reason"] == "estimator_failed"


def test_a_photo_is_a_file_in_the_apps_dir_never_bytes_in_the_store():
    assert nu.apply_action("log_meal", {"photo": "../../etc/passwd"})["error"] == "photo_not_found"
    assert nu.apply_action("log_meal", {"photo": "up_missing.jpg"})["error"] == "photo_not_found"
    r = nu.apply_action("log_meal", {"photo": _photo()})
    raw = Path(store.data_dir("nutrition"), "state.json").read_text()
    assert "fake jpeg" not in raw and "base64" not in raw
    meal = next(x for x in nu.view_data()["meals"] if x["id"] == r["meal_id"])
    assert meal["photo_url"] == "/widgets/nutrition/asset/up_0123abcd_meal.jpg"
    manifest = json.loads((APP / "manifest.json").read_text())
    assert manifest["uploads"] is True                         # the host's upload route only serves a declared app


def test_delete_goes_to_the_bin_and_restore_brings_it_back():
    r = nu.apply_action("log_meal", {"text": "toast", "calories": 120})
    assert nu.apply_action("delete_meal", {"meal_id": r["meal_id"]})["ok"]
    assert not nu.view_data()["meals"] and nu.view_data()["bin_n"] == 1
    assert nu.apply_action("restore", {})["restored"] == r["meal_id"]
    assert [m["id"] for m in nu.view_data()["meals"]] == [r["meal_id"]]


def test_the_door_is_the_only_way_out():
    """No provider, no key, no network anywhere in the app: the prompts are data and `estimate` is the one caller."""
    src = "\n".join(p.read_text() for p in APP.rglob("*.py"))
    assert not re.search(r"\b(urllib|http\.client|requests|httpx|socket|aiohttp)\b", src)
    assert not re.search(r"(?i)api[_-]?key|os\.environ|getenv", src)
    calls = re.findall(r"_d\.estimate\(\s*\"(\w+)\"", src)
    assert sorted(calls) == ["evaluation", "meal", "menu_coach"]           # one caller per kind, all through the door
    assert all("MODEL_DOOR" not in (APP / f).read_text() for f in ("actions.py", "body.py", "advice.py", "day.py"))
    for kind in ("meal", "evaluation", "menu_coach"):
        assert kind in nu.prompts()
    js = "\n".join(p.read_text() for p in APP.rglob("*.js"))
    assert not re.search(r"\b(fetch|XMLHttpRequest|WebSocket|EventSource)\b", js)
