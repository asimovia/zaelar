"""Muscle recovery map — the original app's `api/src/muscle-state.js` ported 1:1 (V2-900).

Exercise key → muscle groups (primary counts 1.0 per set, secondary 0.5). An exercise not in the map is inferred
from its name (a simple heuristic, ES + EN words). Two scores from the same sets, over a 21-day horizon:

- `building_score` −5 (losing muscle) … +5 (building). High is good: more recent work.
- `opportunity_score` −5 (just trained, acute fatigue) … +5 (needs training now). 0 is the optimal window to train
  the group again; it captures the opportunity cost of waiting even once «recovered».

The group ids are English identifiers; their labels are the card's (`widgets.gym.muscle_<id>`). The state ids
are the English names of the original app's states (construyendo → building, ventana-cerrando → window_closing, …).
"""
from __future__ import annotations

import re
import time

MUSCLE_GROUPS = ["chest", "back", "shoulders", "biceps", "triceps", "quads", "hamstrings", "glutes", "calves",
                 "core", "traps"]

EXERCISE_MUSCLES = {
    "cable-row":           {"primary": ["back"], "secondary": ["biceps"]},
    "chest-supported-row": {"primary": ["back"], "secondary": ["biceps"]},
    "db-bench":            {"primary": ["chest"], "secondary": ["triceps", "shoulders"]},
    "db-bench-heavy":      {"primary": ["chest"], "secondary": ["triceps", "shoulders"]},
    "db-curl":             {"primary": ["biceps"], "secondary": []},
    "db-shoulder-press":   {"primary": ["shoulders"], "secondary": ["triceps"]},
    "db-shrugs":           {"primary": ["traps"], "secondary": []},
    "farmer-carry":        {"primary": ["traps", "core"], "secondary": []},
    "goblet-squat":        {"primary": ["quads"], "secondary": ["glutes", "core"]},
    "hammer-curl":         {"primary": ["biceps"], "secondary": []},
    "incline-db":          {"primary": ["chest", "shoulders"], "secondary": ["triceps"]},
    "kb-swing":            {"primary": ["glutes"], "secondary": ["hamstrings", "core"]},
    "lat-pulldown":        {"primary": ["back"], "secondary": ["biceps"]},
    "leg-curl-seat":       {"primary": ["hamstrings"], "secondary": []},
    "leg-press":           {"primary": ["quads"], "secondary": ["glutes"]},
    "machine-chest":       {"primary": ["chest"], "secondary": ["triceps"]},
    "plank":               {"primary": ["core"], "secondary": []},
    "pullup-assisted":     {"primary": ["back"], "secondary": ["biceps"]},
    "pushups":             {"primary": ["chest"], "secondary": ["triceps", "shoulders"]},
    "rdl-db":              {"primary": ["hamstrings", "glutes"], "secondary": ["back"]},
    "ring-rows":           {"primary": ["back"], "secondary": ["biceps"]},
    "rope-pushdown":       {"primary": ["triceps"], "secondary": []},
    "seated-row":          {"primary": ["back"], "secondary": ["biceps"]},
    "shoulder-press":      {"primary": ["shoulders"], "secondary": ["triceps"]},
    "sled-push":           {"primary": ["quads"], "secondary": ["glutes", "core"]},
    "thrusters":           {"primary": ["shoulders", "quads"], "secondary": ["glutes"]},
    "walking-lunges":      {"primary": ["quads"], "secondary": ["glutes", "hamstrings"]},
    "weighted-pulldown":   {"primary": ["back"], "secondary": ["biceps"]},
}

# The name heuristic, in the original app's order (the first match wins). Spanish words kept, English ones beside them.
_INFER = [
    (r"press.*banca|bench press|pectoral|chest|push.?up|flexion|fondo|\bdips?\b",
     {"primary": ["chest"], "secondary": ["triceps", "shoulders"]}),
    (r"jalon|pull.?up|domin|remo|row|pulldown|lat", {"primary": ["back"], "secondary": ["biceps"]}),
    (r"curl.*biceps|biceps|bicep|martillo|hammer", {"primary": ["biceps"], "secondary": []}),
    (r"triceps|pushdown|frances|skull", {"primary": ["triceps"], "secondary": []}),
    (r"hombro|shoulder|press militar|military press|lateral|deltoid", {"primary": ["shoulders"], "secondary": ["triceps"]}),
    (r"sentadilla|squat|prensa|leg press", {"primary": ["quads"], "secondary": ["glutes"]}),
    (r"femoral|hamstring|isquio|leg curl", {"primary": ["hamstrings"], "secondary": []}),
    (r"peso muerto|deadlift|rdl", {"primary": ["hamstrings", "glutes"], "secondary": ["back"]}),
    (r"hip thrust|gluteo|glute", {"primary": ["glutes"], "secondary": ["hamstrings"]}),
    (r"swing|kettlebell", {"primary": ["glutes"], "secondary": ["hamstrings", "core"]}),
    (r"lunge|zancada|step.?up", {"primary": ["quads"], "secondary": ["glutes", "hamstrings"]}),
    (r"gemelo|calf|calves", {"primary": ["calves"], "secondary": []}),
    (r"plancha|plank|abdom|crunch|core", {"primary": ["core"], "secondary": []}),
    (r"shrug|encogimiento|trapec", {"primary": ["traps"], "secondary": []}),
    (r"farmer|carry|paseo", {"primary": ["traps", "core"], "secondary": []}),
]
_ACCENTS = str.maketrans("áéíóúüñ", "aeiouun")


def _infer_from_name(name) -> dict | None:
    if not name:
        return None
    n = str(name).lower().translate(_ACCENTS)
    for rx, muscles in _INFER:
        if re.search(rx, n):
            return muscles
    return None


def muscles_for_exercise(key, name) -> dict | None:
    return EXERCISE_MUSCLES.get(key or "") or _infer_from_name(name)


def compute_muscle_state(sets, now: float | None = None) -> list[dict]:
    """sets: [{exercise_key, exercise_name, muscle_key?, completed_at (epoch s), reps_done, weight_kg}].
    `muscle_key` is the program exercise an alternative stood in for: its muscles are the ones that worked."""
    horizon_days = 21
    now = time.time() if now is None else now
    groups = {m: {"sets_7d": 0.0, "sets_14d": 0.0, "volume_7d": 0.0, "last_hit": 0.0} for m in MUSCLE_GROUPS}
    for s in sets or []:
        ts = float(s.get("completed_at") or 0)
        if not ts:
            continue
        age_days = (now - ts) / 86400
        if age_days > horizon_days:
            continue
        muscles = (muscles_for_exercise(s.get("muscle_key"), None) if s.get("muscle_key") else None) \
            or muscles_for_exercise(s.get("exercise_key"), s.get("exercise_name"))
        if not muscles:
            continue
        reps = _num(s.get("reps_done"))
        w = _num(s.get("weight_kg"))
        vol = reps * (w if w > 0 else 1)          # bodyweight counts as 1

        def add(grp, weight):
            g = groups.get(grp)
            if not g:
                return
            if age_days <= 7:
                g["sets_7d"] += weight
                g["volume_7d"] += vol * weight
            if age_days <= 14:
                g["sets_14d"] += weight
            g["last_hit"] = max(g["last_hit"], ts)

        for grp in muscles.get("primary") or []:
            add(grp, 1.0)
        for grp in muscles.get("secondary") or []:
            add(grp, 0.5)

    out = []
    for m in MUSCLE_GROUPS:
        g = groups[m]
        never = not g["last_hit"]
        last_days = 999 if never else (now - g["last_hit"]) / 86400
        if last_days > 14:
            b_score, b_state = -5, "losing"
        elif last_days > 10:
            b_score, b_state = -3, "falling"
        elif last_days > 7:
            b_score, b_state = -1, "standby"
        else:
            s7 = g["sets_7d"]
            if s7 >= 10:
                b_score, b_state = 5, "building"
            elif s7 >= 7:
                b_score, b_state = 4, "building"
            elif s7 >= 5:
                b_score, b_state = 3, "growing"
            elif s7 >= 3:
                b_score, b_state = 2, "growing"
            elif s7 >= 1:
                b_score, b_state = 1, "touched"
            else:
                b_score, b_state = 0, "standby"
        # opportunity: 0-1d −5 fatigued · 1-2d −3 recovering · 2-4d 0 optimal · 4-6d +1 window closing ·
        # 6-9d +3 train soon · 9-12d +4 urgent · 12+d or never +5
        if never:
            o_score, o_state = 5, "no_data"
        elif last_days > 12:
            o_score, o_state = 5, "critical"
        elif last_days > 9:
            o_score, o_state = 4, "urgent"
        elif last_days > 6:
            o_score, o_state = 3, "train_soon"
        elif last_days > 4:
            o_score, o_state = 1, "window_closing"
        elif last_days > 2:
            o_score, o_state = 0, "optimal"
        elif last_days > 1:
            o_score, o_state = -3, "recovering"
        else:
            o_score, o_state = -5, "fatigued"
        out.append({
            "muscle": m,
            "building_score": b_score, "building_state": b_state,
            "opportunity_score": o_score, "opportunity_state": o_state,
            "sets_7d": round(g["sets_7d"], 1), "sets_14d": round(g["sets_14d"], 1),
            "days_since": None if last_days > 90 else round(last_days, 1),
        })
    return out


def _num(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0
