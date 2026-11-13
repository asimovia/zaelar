"""Nutrition — the numbers of a day, ported 1:1 from the source PWA (V2-899). Pure: no store, no I/O but the
components table it reads from this folder.

The logical day starts at 03:00; timestamps are the person's LOCAL clock as their screen sends it. Targets are
Mifflin-St Jeor x 1.55 x the goal factor; the day's light, its 0-100 score and its components are the source's.
Every rounding a source number went through is JavaScript's Math.round (`jround`).
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
DAY_START_HOUR = 3            # a meal at 02:30 still belongs to yesterday
DAYS_VIEW = 30                # the per-day strip (quality light, weight chart)
GOALS = ("gain", "lose", "maintain")
# The source's defaults when the profile is empty (they make the targets readable before he fills anything).
DEFAULTS = {"weight_kg": 75.0, "height_cm": 175.0, "age": 30, "protein_per_kg": 2.0, "surplus_pct": 15.0,
            "goal": "gain"}


# ── time: naive LOCAL clock strings, as the person's screen sends them ─────────────────────────────────────────
_ISO = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?")


def now_local() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def clean_when(v, fallback: str | None = None) -> str | None:
    """A local timestamp `YYYY-MM-DDTHH:MM[:SS]` (also with a space) normalised to seconds; anything else -> fallback."""
    m = _ISO.match(str(v or "").strip())
    if not m:
        return fallback
    try:
        dt = datetime.strptime(f"{m.group(1)}T{m.group(2)}:{m.group(3)}:{m.group(4) or '00'}", "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return fallback
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def logical_day(when: str | None) -> str | None:
    """The day a timestamp counts for: the day starts at 03:00 (source rule)."""
    w = clean_when(when)
    if not w:
        return None
    return (datetime.strptime(w, "%Y-%m-%dT%H:%M:%S") - timedelta(hours=DAY_START_HOUR)).strftime("%Y-%m-%d")


def hour_of(when: str | None) -> int | None:
    w = clean_when(when)
    return int(w[11:13]) if w else None


def _num(v, lo=None, hi=None):
    """A number from a value a person typed or said («75,8» or 75.8); None when it is not one or out of range."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, str):
        v = v.strip().replace(",", ".")
        if not v:
            return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n != n or n in (float("inf"), float("-inf")):
        return None
    if (lo is not None and n < lo) or (hi is not None and n > hi):
        return None
    return n


def jround(x: float) -> int:
    """JavaScript's Math.round (half up). Python's round() is half-to-even, so 14.5 would be 14 here and 15 in the
    source; every number ported from it rounds through this."""
    return int(math.floor(x + 0.5))


def clamp_score(v) -> int | None:
    n = _num(v)
    return None if n is None else max(1, min(5, jround(n)))


# ── targets (ported 1:1) ───────────────────────────────────────────────────────────────────────────────────────
def profile_of(db: dict) -> dict:
    p = dict(db.get("profile") or {})
    return p


def bmr(weight_kg: float, height_cm: float, age: float, sex: str = "male") -> float:
    """Mifflin-St Jeor. The source had only the male constant (+5); `female` (-161) is the one addition, and an
    unknown sex keeps the source's +5 so a profile without it gives exactly the source's numbers."""
    return 10 * weight_kg + 6.25 * height_cm - 5 * age + (-161 if sex == "female" else 5)


def real_avg_burn(burned_days: list | None) -> int | None:
    """Mean of the last 14 days with a measured burn, when there are at least 3 (source: `realAvgBurn`). The days
    come from a health source the core does not hand to apps yet, so today this is always None (formula)."""
    vals = [float(x) for x in (burned_days or []) if isinstance(x, (int, float)) and x > 0][-14:]
    return jround(sum(vals) / len(vals)) if len(vals) >= 3 else None


def targets(profile: dict, burned_days: list | None = None) -> dict:
    w = _num(profile.get("weight_kg")) or DEFAULTS["weight_kg"]
    h = _num(profile.get("height_cm")) or DEFAULTS["height_cm"]
    age = _num(profile.get("age")) or DEFAULTS["age"]
    ppk = _num(profile.get("protein_per_kg")) or DEFAULTS["protein_per_kg"]
    pct = (_num(profile.get("surplus_pct")) or DEFAULTS["surplus_pct"]) / 100
    goal = profile.get("goal") if profile.get("goal") in GOALS else DEFAULTS["goal"]
    real = real_avg_burn(burned_days)
    tdee = real if real is not None else jround(bmr(w, h, age, str(profile.get("sex") or "")) * 1.55)
    factor = (1 - pct) if goal == "lose" else 1 if goal == "maintain" else (1 + pct)
    return {
        "calories": int(_num(profile.get("target_calories")) or jround(tdee * factor)),
        "protein_g": int(_num(profile.get("target_protein_g")) or jround(w * ppk)),
        "tdee": int(tdee), "tdee_source": "real" if real is not None else "formula", "goal": goal,
        "calories_set_by_hand": bool(_num(profile.get("target_calories"))),
    }


def goal_status(kcal_in: float, target: float) -> str:
    """on (within ±5 %, at least ±80 kcal) | low | over — the source's home goal card."""
    if not target:
        return "low"
    d = jround(kcal_in - target)
    if abs(d) <= max(80, target * 0.05):
        return "on"
    return "over" if d > 0 else "low"


# ── a day: totals, quality, components, score (ported 1:1) ────────────────────────────────────────────────────
def counts(m: dict) -> bool:
    """A meal that counts for the day's totals: not pending, and with calories (source: `todayMealsValid`)."""
    return m.get("status") != "pending" and (_num(m.get("calories")) or 0) > 0


def totals(meals: list) -> dict:
    t = {k: 0.0 for k in ("calories", "protein_g", "carbs_g", "fat_g", "fiber_g")}
    for m in meals:
        if counts(m):
            for k in t:
                t[k] += _num(m.get(k)) or 0
    return {k: round(v, 1) for k, v in t.items()}


def health_avg(meals: list) -> float | None:
    """kcal-weighted mean of health_score (1-5) over the scored meals; None when none is scored."""
    w = s = 0.0
    for m in meals:
        hs = clamp_score(m.get("health_score"))
        if hs is None or m.get("status") == "pending":
            continue
        weight = max(1.0, _num(m.get("calories")) or 1.0)
        w += weight
        s += weight * hs
    return s / w if w else None


def quality_label(avg: float | None) -> str:
    if avg is None:
        return "none"
    return "high" if avg >= 4.0 else "medium" if avg >= 3.0 else "low" if avg >= 2.0 else "very_low"


def meal_rating(m: dict) -> str:
    hs = clamp_score(m.get("health_score"))
    return "" if hs is None else "green" if hs >= 4 else "yellow" if hs >= 3 else "red"


# Lunch and dinner windows by LOCAL hour. The source counted 11-15 / 18-22 on UTC clock hours of a Madrid user,
# i.e. 12-16 / 19-23 local in winter; this store keeps the person's local clock, so the local windows are used.
LUNCH_HOURS, DINNER_HOURS = range(12, 17), range(19, 24)


def day_rating(meals: list) -> dict:
    """The day's traffic light (source: /api/stats/days): only with lunch AND dinner logged; green >= 4.0, yellow >=
    3.0, red below, grey when incomplete or unscored."""
    valid = [m for m in meals if (_num(m.get("calories")) or 0) > 0 and m.get("status") != "pending"]
    lunch = sum(1 for m in valid if hour_of(m.get("eaten_at")) in LUNCH_HOURS)
    dinner = sum(1 for m in valid if hour_of(m.get("eaten_at")) in DINNER_HOURS)
    avg = health_avg(valid)
    rating = "gray"
    if lunch and dinner and avg is not None:
        rating = "green" if avg >= 4.0 else "yellow" if avg >= 3.0 else "red"
    return {"rating": rating, "has_main_meals": bool(lunch and dinner), "health_avg": None if avg is None else jround(avg * 10) / 10}


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(s or "").lower()) if not unicodedata.combining(c))


def _components_spec() -> dict:
    try:
        return json.loads((HERE / "components.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — a missing table means no variety credit, never a broken day
        return {"components": []}


def components(meals: list) -> list[str]:
    """Which of the seven components of a healthy day are present. The estimator's own language-free tags win
    (`estimate.components`); a meal entered by hand falls back to the words of `components.json`."""
    spec = _components_spec().get("components") or []
    keys = [c.get("key") for c in spec if c.get("key")]
    present: set[str] = set()
    text = []
    for m in meals:
        if not counts(m):
            continue
        tags = (m.get("estimate") or {}).get("components")
        if isinstance(tags, list) and tags:
            present.update(str(t) for t in tags if t in keys)
        else:
            text.append(_fold(m.get("description")))
    blob = " " + re.sub(r"[^a-z0-9]+", " ", " ".join(text)) + " "
    for c in spec:
        if c.get("key") in present or not blob.strip():
            continue
        words = [_fold(w).strip() for lang in (c.get("words") or {}).values() for w in lang]
        if any(_said(w, blob) for w in words if w):
            present.add(c["key"])
    return [k for k in keys if k in present]


def _said(word: str, blob: str) -> bool:
    """`stem*` is the start of a word; anything else is a whole word or phrase, plural -s/-es included."""
    if word.endswith("*"):
        return f" {word[:-1]}" in blob
    return any(f" {word}{tail} " in blob for tail in ("", "s", "es"))


def day_score(meals: list, tgt: dict) -> int | None:
    """0-100: protein vs target (35) + variety, components present of 7 (40) + kcal balance (25); capped low before
    600 kcal so a morning does not look perfect (source: `nutScore`)."""
    if not any(counts(m) for m in meals):
        return None
    t = totals(meals)
    prot = min(1.0, t["protein_g"] / (tgt.get("protein_g") or 100)) * 35
    n_comp = len(_components_spec().get("components") or []) or 7
    var = len(components(meals)) / n_comp * 40
    ratio = t["calories"] / (tgt.get("calories") or 2000)
    cal = 25 if 0.85 <= ratio <= 1.10 else 17 if 0.70 <= ratio <= 1.20 else 10 if 0.50 <= ratio <= 1.35 else 4
    if t["calories"] < 600:
        cal = min(cal, 12)
    return jround(prot + var + cal)


def score_class(s: int | None) -> str:
    return "na" if s is None else "good" if s >= 75 else "ok" if s >= 55 else "low"




# ── the per-day strip ─────────────────────────────────────────────────────────────────────────────────────────
def days_view(db: dict, tgt: dict, today: str, n: int = DAYS_VIEW) -> list:
    by_day: dict[str, list] = {}
    for m in db.get("meals") or []:
        d = logical_day(m.get("eaten_at"))
        if d:
            by_day.setdefault(d, []).append(m)
    weight_by_day: dict[str, dict] = {}
    for b in sorted(db.get("body") or [], key=lambda r: r.get("measured_at") or ""):
        d = logical_day(b.get("measured_at"))
        if d and _num(b.get("weight_kg")) is not None:
            weight_by_day[d] = b
    out = []
    t0 = datetime.strptime(today, "%Y-%m-%d")
    for i in range(n - 1, -1, -1):
        d = (t0 - timedelta(days=i)).strftime("%Y-%m-%d")
        ms = by_day.get(d, [])
        t = totals(ms)
        b = weight_by_day.get(d) or {}
        out.append({"date": d, "kcal_in": jround(t["calories"]), "protein_g": jround(t["protein_g"]),
                    "carbs_g": jround(t["carbs_g"]), "fat_g": jround(t["fat_g"]), "fiber_g": jround(t["fiber_g"]),
                    "meals_n": sum(1 for m in ms if m.get("status") != "pending"),
                    "pending_n": sum(1 for m in ms if m.get("status") == "pending"),
                    "score": day_score(ms, tgt), "components": components(ms),
                    "goal_status": goal_status(t["calories"], tgt["calories"]) if ms else None,
                    "weight_kg": _num(b.get("weight_kg")), "body_fat_pct": _num(b.get("body_fat_pct")),
                    **day_rating(ms)})
    return out
