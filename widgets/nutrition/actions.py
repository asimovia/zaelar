"""Nutrition — the meal handlers and the shared helpers (the table the gate reads is `data.ACTIONS`; the body log and
the profile are in `body.py`, the weekly evaluation and the menu coach in `advice.py`).

Each handler is `(action, payload) -> dict`, loads the store, changes it and saves once. They read `data` through an
alias so the circular import (data imports these names back for its table) resolves at call time.
"""
from __future__ import annotations

from . import data as _d

REFINE_MARK = "[Refinement from the person]: "


def _find(rows: list, rid) -> dict | None:
    rid = str(rid or "")
    return next((r for r in rows if str(r.get("id")) == rid), None) if rid else None


def _lang(db: dict, p: dict) -> str:
    """The language the estimate's words come back in: the card sends the screen's; kept for voice-made rows."""
    lang = str(p.get("lang") or "").strip()[:8]
    if lang:
        db["lang"] = lang
    return db.get("lang") or "en"


# ── the estimate of one meal ───────────────────────────────────────────────────────────────────────────────────
def apply_estimate(meal: dict, out) -> str | None:
    """Write a model's answer onto the meal (source: processMealLLM). Returns an error code, or None when applied."""
    if not isinstance(out, dict):
        return "estimator_bad_answer"
    t = out.get("totals") if isinstance(out.get("totals"), dict) else {}
    conf = _d._num(out.get("confidence")) or 0
    if meal.get("photo") and (_d._num(t.get("calories")) or 0) < 5 and conf < 0.3:
        return "no_food_identified"           # source: a photo with no food is a failure, never a 0 kcal meal
    meal["description"] = str(out.get("description") or "").strip()[:80] or None
    meal["grams"] = _d._num(t.get("grams"))
    for k in ("calories", "protein_g", "carbs_g", "fat_g"):
        meal[k] = _d._num(t.get(k)) or 0
    meal["fiber_g"] = _d._num(t.get("fiber_g"))
    meal["health_score"] = _d.clamp_score(out.get("health_score"))
    hr = out.get("health_reason")
    meal["health_reason"] = hr.strip()[:100] if isinstance(hr, str) else None
    ings = out.get("ingredients") if isinstance(out.get("ingredients"), list) else []
    comps = out.get("components") if isinstance(out.get("components"), list) else []
    meal["estimate"] = {"ingredients": [i for i in ings if isinstance(i, dict)][:30], "confidence": conf,
                        "notes": str(out.get("notes") or "")[:1200], "components": [str(c) for c in comps][:7]}
    meal["status"], meal["error"] = "done", None
    return None


def _run_estimate(db: dict, meal: dict) -> None:
    text = (meal.get("source_text") or "").strip()
    photo = _d.photo_path(meal.get("photo")) if meal.get("photo") else None
    if meal.get("photo") and not photo:
        meal["status"], meal["error"] = "failed", "photo_not_found"
        return
    user_key = "user_photo_text" if photo and text else "user_photo" if photo else "user_text"
    res = _d.estimate("meal", {"text": text, "lang": db.get("lang") or "en",
                               "images": [str(photo)] if photo else []}, user_key=user_key)
    err = apply_estimate(meal, res["out"]) if res.get("ok") else res.get("error") or "estimator_failed"
    if err:
        meal["status"], meal["error"] = "failed", err


def _a_log_meal(action: str, p: dict) -> dict:
    db = _d.load()
    lang = _lang(db, p)
    text = str(p.get("text") or "").strip()[:2000]
    photo = str(p.get("photo") or "").strip()
    desc = str(p.get("description") or "").strip()[:80]
    kcal = _d._num(p.get("calories"), 0, 10000)
    if photo and not _d.photo_path(photo):
        return {"ok": False, "error": "photo_not_found"}
    if not (text or photo or desc):
        return {"ok": False, "error": "nothing_to_log", "hint": "a photo, a sentence or a description"}
    now = _d.now_local()
    meal = {"id": _d.next_id(db, "m"), "created_at": now, "eaten_at": _d.clean_when(p.get("eaten_at"), now),
            "source": "photo" if photo else "text" if text else "manual", "description": desc or None,
            "source_text": text or None, "photo": photo or None, "status": "pending", "error": None}
    if kcal is not None:                       # numbers he gave: the meal is done, no estimate is asked
        for k in ("grams", "protein_g", "carbs_g", "fat_g", "fiber_g"):
            meal[k] = _d._num(p.get(k), 0, 10000)
        meal["calories"] = kcal
        meal["health_score"] = _d.clamp_score(p.get("health_score"))
        meal["health_reason"] = str(p.get("health_reason") or "")[:100] or None
        meal["description"] = desc or (text[:80] if text else None)
        meal["status"] = "done"
    else:
        _run_estimate(db, meal)
    db["meals"].append(meal)
    db["view"] = {**(db.get("view") or {}), "screen": "today", "day": _d.logical_day(meal["eaten_at"])}
    _d.save(db)
    out = {"ok": True, "meal_id": meal["id"], "status": meal["status"], "lang": lang}
    if meal["status"] == "failed":
        out.update({"estimated": False, "reason": meal["error"],
                    "note": "saved; the calories can be entered by hand (edit_meal) or retried later"})
    return out


def _a_retry_meal(action: str, p: dict) -> dict:
    db = _d.load()
    _lang(db, p)
    meal = _find(db["meals"], p.get("meal_id"))
    if not meal:
        return {"ok": False, "error": "meal_not_found"}
    if not meal.get("source_text") and not meal.get("photo"):
        return {"ok": False, "error": "no_source", "note": "a meal entered by hand has nothing to estimate from"}
    meal["status"], meal["error"] = "pending", None
    _run_estimate(db, meal)
    _d.save(db)
    return {"ok": meal["status"] == "done", "meal_id": meal["id"], "status": meal["status"], "error": meal["error"]}


def _a_refine_meal(action: str, p: dict) -> dict:
    db = _d.load()
    _lang(db, p)
    meal = _find(db["meals"], p.get("meal_id"))
    if not meal:
        return {"ok": False, "error": "meal_not_found"}
    extra = str(p.get("text") or "").strip()[:1000]
    when = _d.clean_when(p.get("eaten_at"))
    if not extra and not when:
        return {"ok": False, "error": "nothing_to_refine", "hint": "text and/or eaten_at"}
    if when:
        meal["eaten_at"] = when                # the time alone never asks for a new estimate (source rule)
    if extra:
        prev = (meal.get("source_text") or "").strip()
        meal["source_text"] = f"{prev}\n{REFINE_MARK}{extra}" if prev else extra
        meal["status"], meal["error"] = "pending", None
        _run_estimate(db, meal)
    _d.save(db)
    return {"ok": True, "meal_id": meal["id"], "status": meal["status"], "error": meal.get("error")}


def _a_edit_meal(action: str, p: dict) -> dict:
    db = _d.load()
    meal = _find(db["meals"], p.get("meal_id"))
    if not meal:
        return {"ok": False, "error": "meal_not_found"}
    changed = []
    if "description" in p:
        meal["description"] = str(p.get("description") or "").strip()[:80] or None
        changed.append("description")
    for k in _d.NUM_FIELDS:
        if k in p:
            meal[k] = _d._num(p.get(k), 0, 10000)
            changed.append(k)
    if "health_score" in p:
        meal["health_score"] = _d.clamp_score(p.get("health_score"))
        changed.append("health_score")
    if "health_reason" in p:
        meal["health_reason"] = str(p.get("health_reason") or "")[:100] or None
        changed.append("health_reason")
    when = _d.clean_when(p.get("eaten_at"))
    if when:
        meal["eaten_at"] = when
        changed.append("eaten_at")
    if not changed:
        return {"ok": True, "meal_id": meal["id"], "changed": []}
    if meal.get("calories") is None:
        meal["calories"] = 0
    meal["status"], meal["error"] = "done", None      # a correction by hand is the truth (source: PATCH)
    _d.save(db)
    return {"ok": True, "meal_id": meal["id"], "changed": changed, "status": "done"}


def _to_bin(db: dict, kind: str, row: dict) -> None:
    db["bin"] = ([{"kind": kind, "row": row, "deleted_at": _d.now_local()}] + (db.get("bin") or []))
    for gone in db["bin"][_d.BIN_MAX:]:                 # a photo leaves the disk only when its row leaves the bin
        name = (gone.get("row") or {}).get("photo")
        path = _d.photo_path(name) if name else None
        if path:
            try:
                path.unlink()
            except OSError:
                pass
    db["bin"] = db["bin"][:_d.BIN_MAX]


def _a_delete_meal(action: str, p: dict) -> dict:
    db = _d.load()
    meal = _find(db["meals"], p.get("meal_id"))
    if not meal:
        return {"ok": False, "error": "meal_not_found"}
    db["meals"] = [m for m in db["meals"] if m is not meal]
    _to_bin(db, "meal", meal)
    if (db.get("view") or {}).get("meal") == meal["id"]:
        db["view"]["meal"] = None
    _d.save(db)
    return {"ok": True, "deleted": meal["id"], "undo": {"action": "restore", "payload": {"id": meal["id"]}}}


def _sync_profile_weight(db: dict) -> None:
    """The latest weighed entry is the profile's current weight (source: POST/PATCH/DELETE /api/body)."""
    rows = sorted((b for b in db.get("body") or [] if _d._num(b.get("weight_kg")) is not None),
                  key=lambda r: r.get("measured_at") or "")
    if rows:
        db["profile"]["weight_kg"] = _d._num(rows[-1]["weight_kg"])


def _a_restore(action: str, p: dict) -> dict:
    db = _d.load()
    bin_ = db.get("bin") or []
    rid = str(p.get("id") or "")
    hit = next((b for b in bin_ if str((b.get("row") or {}).get("id")) == rid), None) if rid else (bin_[0] if bin_ else None)
    if not hit:
        return {"ok": False, "error": "nothing_to_restore"}
    db["bin"] = [b for b in bin_ if b is not hit]
    (db["meals"] if hit["kind"] == "meal" else db["body"]).append(hit["row"])
    if hit["kind"] == "weight":
        _sync_profile_weight(db)
    _d.save(db)
    return {"ok": True, "restored": hit["row"].get("id"), "kind": hit["kind"]}


def _a_show(action: str, p: dict) -> dict:
    db = _d.load()
    v = dict(db.get("view") or {})
    screen = str(p.get("screen") or "").strip()
    if screen:
        if screen not in _d.SCREENS:
            return {"ok": False, "error": "unknown_screen", "screens": list(_d.SCREENS)}
        v["screen"] = screen
    if "day" in p:
        day = str(p.get("day") or "").strip()
        if day in ("", "today"):
            v["day"] = None
        elif _d.clean_when(day + "T12:00"):
            v["day"] = day
        else:
            return {"ok": False, "error": "bad_day", "hint": "YYYY-MM-DD"}
    if "meal_id" in p:
        mid = str(p.get("meal_id") or "")
        meal = _find(db["meals"], mid) if mid else None
        if mid and not meal:
            return {"ok": False, "error": "meal_not_found"}
        v["meal"] = meal["id"] if meal else None
        if meal:
            v["screen"], v["day"] = "today", _d.logical_day(meal.get("eaten_at"))
    v["n"] = int(v.get("n") or 0) + 1          # the same order said twice moves the card twice
    db["view"] = v
    _d.save(db)
    return {"ok": True, "view": v}
