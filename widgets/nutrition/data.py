"""Nutrition — meals by photo or dictation, calories and macros, daily targets, the weight log (V2-899).

Ported from a previous single-user PWA whose nutrition area was in daily use; the behaviour is kept 1:1 where the
source had it: the daily targets (Mifflin-St Jeor BMR x 1.55, goal factor, protein g/kg), the day's balance, the
kcal-weighted health average and its traffic light, the 0-100 day score (protein 35 + variety 40 + kcal balance 25),
the logical day that starts at 03:00, and the meal lifecycle pending -> done | failed with retry and refine.

Storage: the shared per-widget store (`store.load/save`) for rows; photos are files in `store.data_dir(WID)` (they
arrive through the card's `ctx.upload`, never as base64 in state.json). One person, no user ids.

THE MODEL DOOR. Estimating a meal from a photo or a sentence, the weekly evaluation and the menu coach need a
language model. There is no model seam for apps yet, so every such call goes through ONE function, `estimate()`,
which today answers `estimator_unavailable`; the meal stays editable by hand. The prompts and their output shapes
live in `prompts.json` (data), so wiring the door is the only change left. Nothing here calls a provider or reads
a key.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from .. import store
from .day import (  # noqa: F401 — the day's numbers, read by the actions and the tests as `data.<name>`
    DAY_START_HOUR, DAYS_VIEW, DEFAULTS, DINNER_HOURS, GOALS, LUNCH_HOURS, _components_spec, _num, bmr, clamp_score,
    clean_when, components, counts, day_rating, day_score, days_view, goal_status, health_avg, hour_of, jround,
    logical_day, meal_rating, now_local, profile_of, quality_label, real_avg_burn, score_class, targets, totals,
)

WID = "nutrition"
DB_VERSION = 1
HERE = Path(__file__).resolve().parent
MEALS_VIEW_DAYS = 14          # meals sent to the card
BODY_VIEW = 60
BIN_MAX = 20
EVAL_KEEP = 20
SCREENS = ("today", "weight", "coach", "evaluation", "profile")
SEXES = ("male", "female", "unknown")
MEAL_STATUS = ("pending", "done", "failed")
NUM_FIELDS = ("grams", "calories", "protein_g", "carbs_g", "fat_g", "fiber_g")
BODY_FIELDS = ("weight_kg", "body_fat_pct", "muscle_mass_kg", "waist_cm")
PROFILE_NUM = {"weight_kg": (20, 400), "height_cm": (80, 250), "age": (5, 120), "surplus_pct": (0, 50),
               "protein_per_kg": (0.5, 4.0), "target_calories": (800, 8000), "target_protein_g": (20, 500),
               "target_weight_kg": (20, 400), "body_fat_pct": (2, 70)}


# ── store ──────────────────────────────────────────────────────────────────────────────────────────────────────
def _default() -> dict:
    return {"_v": DB_VERSION, "seq": 0, "profile": {}, "meals": [], "body": [], "evaluations": [], "bin": [],
            "coach": None, "evaluating": None, "view": {"screen": "today", "day": None, "meal": None}}


def _migrate(db: dict, _from_v) -> dict:
    return db


def load() -> dict:
    db = store.load(WID, _default(), version=DB_VERSION, migrate=_migrate)
    for k, v in _default().items():
        db.setdefault(k, v)
    return db


def save(db: dict) -> None:
    store.save(WID, db)


def next_id(db: dict, prefix: str) -> str:
    db["seq"] = int(db.get("seq") or 0) + 1
    return f"{prefix}{db['seq']}"


# ── the model door ─────────────────────────────────────────────────────────────────────────────────────────────
#: Set by the core in phase I (V2-902 I4): a callable `door(request: dict) -> dict` that runs a model and returns
#: its parsed JSON. None today: every estimate answers `estimator_unavailable` and nothing leaves this process.
MODEL_DOOR = None


def prompts() -> dict:
    try:
        return json.loads((HERE / "prompts.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def estimate(kind: str, inputs: dict, user_key: str = "user") -> dict:
    """THE one place this app asks a model. `kind` is a key of `prompts.json` (`meal`, `evaluation`, `menu_coach`);
    `inputs` fills its `user_key` template (a meal has three: text, photo, photo + text). Returns `{"ok": True,
    "out": <parsed JSON or text>}` or `{"ok": False, "error": ...}`; never raises.
    Today there is no door, so it is always `estimator_unavailable`."""
    spec = prompts().get(kind)
    if not isinstance(spec, dict):
        return {"ok": False, "error": "unknown_estimate", "kind": kind}
    door = MODEL_DOOR
    if not callable(door):
        return {"ok": False, "error": "estimator_unavailable"}
    request = {"kind": kind, "system": _fill(spec.get("system", ""), inputs),
               "user": _fill(spec.get(user_key) or spec.get("user", ""), inputs),
               "images": [str(p) for p in (inputs.get("images") or [])], "output": spec.get("output"),
               "json": spec.get("json", True), "max_tokens": spec.get("max_tokens", 1600)}
    try:
        out = door(request)
    except Exception as e:  # noqa: BLE001 — a model failure is a failed estimate, never a dead action
        return {"ok": False, "error": "estimator_failed", "detail": str(e)[:200]}
    if isinstance(out, dict) and out.get("error"):
        return {"ok": False, "error": "estimator_failed", "detail": str(out.get("error"))[:200]}
    return {"ok": True, "out": out}


def _fill(template: str, inputs: dict) -> str:
    def rep(m):
        v = inputs.get(m.group(1))
        return json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else "" if v is None else str(v)
    return re.sub(r"\{(\w+)\}", rep, str(template or ""))


def available() -> bool:
    return callable(MODEL_DOOR)


def photo_path(name: str) -> Path | None:
    """A photo the card uploaded into this app's own data dir; None for anything that is not one."""
    n = str(name or "")
    if not n or "/" in n or "\\" in n or n.startswith(".") or not n.startswith("up_"):
        return None
    p = Path(store.data_dir(WID)) / n
    return p if p.is_file() else None


# ── the view ───────────────────────────────────────────────────────────────────────────────────────────────────
def _meal_view(m: dict) -> dict:
    out = {k: m.get(k) for k in ("id", "eaten_at", "source", "description", "status", "error", "health_reason",
                                 "source_text", "created_at") if k in m}
    for k in NUM_FIELDS:
        out[k] = _num(m.get(k))
    out["health_score"] = clamp_score(m.get("health_score"))
    out["rating"] = meal_rating(m)
    out["day"] = logical_day(m.get("eaten_at"))
    est = m.get("estimate") or {}
    out["ingredients"] = est.get("ingredients") if isinstance(est.get("ingredients"), list) else []
    out["notes"] = str(est.get("notes") or "")[:600]
    out["confidence"] = _num(est.get("confidence"))
    if m.get("photo"):
        out["photo_url"] = f"/widgets/{WID}/asset/{m['photo']}"
    return out


def today_local() -> str:
    return logical_day(now_local()) or datetime.now().strftime("%Y-%m-%d")


def view_data(q: str = "") -> dict:
    try:
        db = load()
        prof = profile_of(db)
        tgt = targets(prof)
        today = today_local()
        since = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=MEALS_VIEW_DAYS)).strftime("%Y-%m-%d")
        meals = [_meal_view(m) for m in db.get("meals") or [] if (logical_day(m.get("eaten_at")) or "") >= since]
        meals.sort(key=lambda m: m.get("eaten_at") or "", reverse=True)
        body = sorted(db.get("body") or [], key=lambda r: r.get("measured_at") or "", reverse=True)[:BODY_VIEW]
        days = days_view(db, tgt, today)
        with_w = [d for d in days if d["weight_kg"] is not None]
        return {
            "today": today, "profile": prof, "targets": tgt, "days": days, "meals": meals,
            "body": body, "weight": {"last": with_w[-1] if with_w else None,
                                     "delta": round(with_w[-1]["weight_kg"] - with_w[0]["weight_kg"], 1)
                                     if len(with_w) >= 2 else None},
            "evaluations": (db.get("evaluations") or [])[:8], "evaluating": db.get("evaluating"),
            "coach": db.get("coach"), "view": db.get("view") or {"screen": "today"},
            "estimator": {"available": available()}, "bin_n": len(db.get("bin") or []),
            "components_all": [c.get("key") for c in _components_spec().get("components") or []],
        }
    except Exception as e:  # noqa: BLE001 — a broken store is an empty card that says so, never a dead turn
        return {"today": None, "profile": {}, "targets": {}, "days": [], "meals": [], "body": [],
                "evaluations": [], "view": {"screen": "today"}, "error": str(e)[:160]}


def ref_index() -> list[dict]:
    """The meals of the last days and the weight entries he can name («the toast», «this morning's weight»)."""
    try:
        db = load()
        since = (datetime.strptime(today_local(), "%Y-%m-%d") - timedelta(days=3)).strftime("%Y-%m-%d")
        out = []
        for m in sorted(db.get("meals") or [], key=lambda r: r.get("eaten_at") or "", reverse=True):
            if (logical_day(m.get("eaten_at")) or "") < since:
                continue
            out.append({"id": m["id"], "label": str(m.get("description") or m.get("source_text") or "")[:60],
                        "field": "meal_id", "hint": str(m.get("eaten_at") or "")[:16].replace("T", " ")})
        for b in sorted(db.get("body") or [], key=lambda r: r.get("measured_at") or "", reverse=True)[:5]:
            out.append({"id": b["id"], "label": f"{b.get('weight_kg')} kg", "field": "entry_id",
                        "hint": str(b.get("measured_at") or "")[:16].replace("T", " ")})
        return out[:40]
    except Exception:  # noqa: BLE001
        return []


def prompt_digest() -> str:
    """With the card open: today's balance, so «how am I doing today?» needs no round trip."""
    try:
        v = view_data()
        d = (v.get("days") or [None])[-1]
        if not d:
            return ""
        t = v["targets"]
        bits = [f"today {d['kcal_in']}/{t['calories']} kcal, protein {d['protein_g']}/{t['protein_g']} g",
                f"{d['meals_n']} meals logged"]
        if d.get("pending_n"):
            bits.append(f"{d['pending_n']} waiting for an estimate")
        if d.get("score") is not None:
            bits.append(f"day score {d['score']}/100")
        w = (v.get("weight") or {}).get("last")
        if w:
            bits.append(f"last weight {w['weight_kg']} kg on {w['date']}")
        if not v.get("estimator", {}).get("available"):
            bits.append("photo/text estimates unavailable: macros are entered by hand")
        return "Nutrition on screen: " + ", ".join(bits) + "."
    except Exception:  # noqa: BLE001 — a broken digest leaves the turn without the figures, never broken
        return ""


# ── the actions (handlers in actions.py, body.py, advice.py; the table the gate reads is here) ────────────────────────────
from .actions import (  # noqa: E402
    _a_delete_meal, _a_edit_meal, _a_log_meal, _a_refine_meal, _a_restore, _a_retry_meal, _a_show,
)
from .advice import _a_coach_menu, _a_evaluate_week  # noqa: E402
from .body import _a_delete_weight, _a_edit_weight, _a_log_weight, _a_set_profile  # noqa: E402

ACTIONS = {
    "log_meal": _a_log_meal,
    "retry_meal": _a_retry_meal,
    "refine_meal": _a_refine_meal,
    "edit_meal": _a_edit_meal,
    "delete_meal": _a_delete_meal,
    "log_weight": _a_log_weight,
    "edit_weight": _a_edit_weight,
    "delete_weight": _a_delete_weight,
    "restore": _a_restore,
    "set_profile": _a_set_profile,
    "evaluate_week": _a_evaluate_week,
    "coach_menu": _a_coach_menu,
    "show": _a_show,
}


def apply_action(action: str, payload: dict) -> dict:
    handler = ACTIONS.get(action) if isinstance(action, str) else None
    if handler is None:
        return {"ok": False, "error": "unknown_action", "action": action}
    try:
        return handler(action, payload if isinstance(payload, dict) else {})
    except Exception as e:  # noqa: BLE001 — an action that breaks says so, never takes the card down
        return {"ok": False, "error": str(e)[:160]}
