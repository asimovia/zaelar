"""«Ready to ride?» — three lights before a ride: legs, food, weather (V2-901, ported from the source app).

The WEATHER light is deterministic and works now: the forecast over the window the ride is expected to last (the
mean of his last five rides, two hours with no history), judged by fixed thresholds. The LEGS and FOOD lights were
a language-model judgement in the source; that call needs the core's model seam (V2-902), so it sits behind ONE
function, `evaluate_with_model`, which answers «not available» until then. Its instructions are kept as DATA in
`readiness_prompt.json`, generalised (no language baked in), ready for the seam.

Labels are not built here: each light carries a `code` and its `params`, and the card says them in the person's
language.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import engine as E
from . import net

TTL_S = 30 * 60
PROMPT_FILE = Path(__file__).with_name("readiness_prompt.json")


def judge_weather(w: dict | None, hours: float) -> dict:
    """The source's heuristic, weighted to sustained heat over the ride: red for rain now, rain ≥70 %, heat ≥30°
    or ≥27° with UV ≥7; yellow for rain 40–70 %, heat ≥26° or cold ≤4°; green otherwise."""
    if not w or not isinstance(w.get("t_now"), (int, float)):
        return {"level": "gray", "code": "no_data", "params": {}}
    horizon = w["horizon"]
    n = max(2, min(horizon, int(-(-hours // 1))))
    temps = [x for x in (w.get("temps") or [])[:n] if isinstance(x, (int, float))]
    probs = [x for x in (w.get("probs") or [])[:n] if isinstance(x, (int, float))]
    uvs = [x for x in (w.get("uv") or [])[:n] if isinstance(x, (int, float))]
    t_now = w["t_now"]
    t_max = max(temps) if temps else t_now
    prob = max(probs) if probs else 0
    uv = max(uvs) if uvs else 0
    dur = E.jround(hours, 1)
    if (w.get("precip_now") or 0) > 0.2:
        lv, code, params = "red", "rain_now", {}
    elif prob >= 70:
        lv, code, params = "red", "rain_likely", {"pct": prob, "hours": dur}
    elif t_max >= 30:
        lv, code, params = "red", "heat", {"temp": E.jround(t_max), "hours": n}
    elif t_max >= 27 and uv >= 7:
        lv, code, params = "red", "heat_uv", {"uv": E.jround(uv)}
    elif prob >= 40:
        lv, code, params = "yellow", "rain_possible", {"pct": prob}
    elif t_max >= 26:
        lv, code, params = "yellow", "warming", {"now": E.jround(t_now), "max": E.jround(t_max), "hours": n}
    elif t_now <= 4:
        lv, code, params = "yellow", "cold", {"temp": E.jround(t_now)}
    else:
        lv, code, params = "green", "stable", {"temp": E.jround(t_now), "hours": dur}
    return {"level": lv, "code": code, "params": params, "temp_now": t_now, "temp_max": t_max,
            "precip_prob_max": prob, "uv_max": uv, "hours_evaluated": n}


def recent_rides(db: dict, now_ms: float) -> list:
    """The rides of the last seven days, as the model was given them in the source."""
    out = []
    for s in sorted(db.get("sessions") or [], key=lambda s: str(s.get("started_at")), reverse=True):
        if s.get("status") != "done" or now_ms - E.ts_ms(s.get("started_at")) > 7 * 86400000:
            continue
        out.append({"hours_ago": E.jround((now_ms - E.ts_ms(s["started_at"])) / 3600000),
                    "km": E.jround(s.get("distance_km") or 0, 1), "min": E.jround((s.get("duration_sec") or 0) / 60),
                    "avg_hr": s.get("avg_hr"), "avg_kmh": s.get("avg_speed_kmh")})
        if len(out) >= 10:
            break
    return out


def avg_duration_hours(db: dict) -> float:
    last = [s.get("duration_sec") or 0 for s in sorted(db.get("sessions") or [], key=lambda s: str(s.get("started_at")),
                                                          reverse=True)
            if s.get("status") == "done" and (s.get("duration_sec") or 0) > 600][:5]
    return (sum(last) / len(last)) / 3600 if last else 2.0


def prompt() -> dict:
    """The model's instructions for the legs and food lights, as data."""
    try:
        return json.loads(PROMPT_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def evaluate_with_model(rides: list, meals: list) -> dict | None:
    """Legs + food lights from a language model. NOT AVAILABLE until the core's model seam exists (V2-902): the
    app may not call a model itself, and meals live in another app. Returns None, and the card says so."""
    return None


def compute(db: dict, lat=None, lng=None, now_ms: float | None = None, weather=net.weather_window) -> dict:
    now_ms = now_ms if now_ms is not None else time.time() * 1000
    if not (isinstance(lat, (int, float)) and isinstance(lng, (int, float))):
        lat = lng = None
        last = sorted((s for s in db.get("sessions") or [] if s.get("start_lat") is not None),
                      key=lambda s: str(s.get("started_at")), reverse=True)
        if last:                                          # the source's fallback: where the last ride started
            lat, lng = last[0]["start_lat"], last[0]["start_lng"]
    hours = avg_duration_hours(db)
    w = weather(lat, lng, hours) if lat is not None else None
    llm = evaluate_with_model(recent_rides(db, now_ms), [])
    unavailable = {"level": "gray", "code": "model_unavailable", "params": {}}
    return {
        "computed_at": E.iso(now_ms),
        "muscle": (llm or {}).get("muscle") or unavailable,
        "nutrition": (llm or {}).get("nutrition") or unavailable,
        "weather": judge_weather(w, hours) if lat is not None else {"level": "gray", "code": "no_place", "params": {}},
        "avg_duration_hours": E.jround(hours, 1),
    }


def fresh(cached: dict | None, now_ms: float | None = None) -> bool:
    if not cached or not cached.get("computed_at"):
        return False
    now_ms = now_ms if now_ms is not None else time.time() * 1000
    return now_ms - E.ts_ms(cached["computed_at"]) < TTL_S * 1000
