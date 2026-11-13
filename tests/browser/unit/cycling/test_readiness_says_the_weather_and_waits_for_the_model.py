"""V2-901 — «ready to ride?»: the weather light is the source's deterministic rule over the ride's usual length;
the legs and food lights wait for the core's model seam (V2-902) and say so, never a guessed green.

Red for rain now, rain ≥ 70 %, heat ≥ 30° or ≥ 27° with UV ≥ 7; yellow for rain 40–70 %, heat ≥ 26° or cold ≤ 4°;
green otherwise. The window is the mean of his last five rides over 10 minutes (two hours with none). With no
position, the place his last ride started. The answer is kept 30 minutes.
"""
from __future__ import annotations

from widgets.cycling import readiness as RD


def _w(t_now, temps=None, probs=None, uv=None, precip_now=0.0, horizon=4):
    return {"horizon": horizon, "t_now": t_now, "precip_now": precip_now, "temps": temps or [t_now] * horizon,
            "probs": probs or [0] * horizon, "uv": uv or [0] * horizon}


def test_the_weather_rule_is_the_sources():
    j = RD.judge_weather
    assert j(_w(18, precip_now=0.5), 2)["code"] == "rain_now"
    assert j(_w(18, probs=[10, 75, 0, 0]), 2)["level"] == "red"
    assert (j(_w(25, temps=[25, 31, 20, 20]), 2)["code"], j(_w(25, temps=[25, 31, 20, 20]), 2)["level"]) == ("heat", "red")
    assert j(_w(27, temps=[27, 28, 27, 27], uv=[7, 8, 0, 0]), 2)["code"] == "heat_uv"
    assert j(_w(18, probs=[45, 0, 0, 0]), 2)["level"] == "yellow"
    assert j(_w(20, temps=[20, 26.5, 0, 0]), 2)["code"] == "warming"
    assert j(_w(3), 2)["code"] == "cold"
    ok = j(_w(18), 2.4)
    assert (ok["level"], ok["code"], ok["params"]) == ("green", "stable", {"temp": 18, "hours": 2.4})
    assert j(_w(18, temps=[18, 18, 31, 31]), 2)["level"] == "green"           # the heat comes after the ride's window
    assert j(None, 2)["level"] == "gray"


def test_legs_and_food_wait_for_the_model_and_the_place_falls_back(cyc):
    asked = []
    db = {"sessions": [{"id": 1, "status": "done", "started_at": "2026-11-12T08:00:00.000Z", "duration_sec": 5400,
                        "start_lat": 41.4, "start_lng": 2.1}]}
    r = RD.compute(db, weather=lambda lat, lng, h: asked.append((lat, lng, h)) or _w(18))
    assert asked == [(41.4, 2.1, 1.5)]                                        # where the last ride started, its length
    assert r["muscle"]["code"] == r["nutrition"]["code"] == "model_unavailable" and r["muscle"]["level"] == "gray"
    assert r["weather"]["level"] == "green" and RD.fresh(r)
    assert RD.compute({"sessions": []}, weather=lambda *a: _w(18))["weather"]["code"] == "no_place"
    assert RD.prompt()["levels"] == ["green", "yellow", "red"]                # the model's instructions travel as data
    first = cyc.apply_action("readiness", {})                                 # offline: the weather says «no data»
    assert first["ok"] and first["weather"]["level"] in ("gray",) and cyc.apply_action("readiness", {})["cached"]
