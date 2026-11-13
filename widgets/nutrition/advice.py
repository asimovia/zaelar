"""Nutrition — the weekly evaluation and the menu coach, built 1:1 from the source and answered by the model door.

Both build the source's context (per-day sums + the last three evaluations; what was eaten, the targets, the margin
and the meal the hour is for) and hand it to `data.estimate`. Without a door they keep nothing but the reason.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from . import data as _d
from .actions import _lang

PHOTOS_MAX = 5              # the menu coach takes up to five photos of a menu (source limit)


def week_context(db: dict, days: int, today: str) -> dict:
    """The evaluation's input (source: POST /api/nutrition/evaluate): per-day sums of the period and the last three
    evaluations, so the model checks progress instead of repeating itself."""
    t0 = datetime.strptime(today, "%Y-%m-%d")
    start = (t0 - timedelta(days=days)).strftime("%Y-%m-%d")
    by: dict[str, dict] = {}
    for m in sorted(db.get("meals") or [], key=lambda r: r.get("eaten_at") or ""):
        d = _d.logical_day(m.get("eaten_at"))
        if not d or d < start or m.get("status") == "pending":
            continue
        row = by.setdefault(d, {"kcal": 0.0, "prot": 0.0, "carbs": 0.0, "fat": 0.0, "fiber": 0.0, "items": []})
        for k, f in (("kcal", "calories"), ("prot", "protein_g"), ("carbs", "carbs_g"), ("fat", "fat_g"), ("fiber", "fiber_g")):
            row[k] += _d._num(m.get(f)) or 0
        row["items"].append(str(m.get("description") or ""))
    tgt = _d.targets(_d.profile_of(db))
    return {
        "goal": tgt["goal"], "target_kcal": tgt["calories"], "target_protein_g": tgt["protein_g"],
        "period": {"start": start, "end": today, "days": days},
        "days": [{"d": d, **{k: round(v[k]) for k in ("kcal", "prot", "carbs", "fat", "fiber")},
                  "items_summary": " · ".join(v["items"][:12])} for d, v in sorted(by.items())],
        "previous_evaluations": [{"period": f"{e.get('period_start')}..{e.get('period_end')}", "score": e.get("score"),
                                  "summary": e.get("summary"), "recommendations": e.get("recommendations") or []}
                                 for e in (db.get("evaluations") or [])[:3]],
    }


def _strings(v, n=8) -> list:
    return [str(x)[:160] for x in v if isinstance(x, (str, int, float))][:n] if isinstance(v, list) else []


def normalise_evaluation(out: dict, ctx: dict) -> dict | None:
    if not isinstance(out, dict):
        return None
    recs = []
    for r in out.get("recommendations") or []:
        if isinstance(r, dict) and r.get("action"):
            pr = _d._num(r.get("priority"))
            recs.append({"action": str(r["action"])[:200], "why": str(r.get("why") or "")[:200],
                         "priority": int(pr) if pr in (1, 2, 3) else 3})
    score = _d._num(out.get("score"), 0, 100)
    return {"period_start": ctx["period"]["start"], "period_end": ctx["period"]["end"],
            "score": int(score) if score is not None else None, "summary": str(out.get("summary") or "")[:400],
            "strengths": _strings(out.get("strengths")), "issues": _strings(out.get("issues")),
            "recommendations": recs[:4]}


def _a_evaluate_week(action: str, p: dict) -> dict:
    db = _d.load()
    lang = _lang(db, p)
    days = int(_d._num(p.get("days"), 1, 14) or 7)
    ctx = week_context(db, days, _d.today_local())
    res = _d.estimate("evaluation", {"context": ctx, "lang": lang})
    ev = normalise_evaluation(res.get("out"), ctx) if res.get("ok") else None
    if not ev:
        db["evaluating"] = {"at": _d.now_local(), "error": res.get("error") or "estimator_bad_answer"}
        _d.save(db)
        return {"ok": False, "error": db["evaluating"]["error"]}
    ev.update({"id": _d.next_id(db, "e"), "evaluated_at": _d.now_local()})
    db["evaluations"] = ([ev] + (db.get("evaluations") or []))[:_d.EVAL_KEEP]
    db["evaluating"] = None
    db["view"] = {**(db.get("view") or {}), "screen": "evaluation"}
    _d.save(db)
    return {"ok": True, "evaluation_id": ev["id"], "score": ev["score"]}


def meal_hint(hour: int) -> str:
    """Which meal the hour is for (source: coach-suggest), as a language-free key."""
    return ("breakfast" if hour < 11 else "mid_morning" if hour < 13 else "lunch" if hour < 16
            else "afternoon_snack" if hour < 19 else "dinner" if hour < 22 else "late_snack")


def day_context(db: dict, at: str) -> dict:
    """The menu coach's view of the day (source: dayCtx): what was eaten, the targets, what is left, the hour."""
    today = _d.logical_day(at) or _d.today_local()
    meals = [m for m in db.get("meals") or [] if _d.logical_day(m.get("eaten_at")) == today]
    t = _d.totals(meals)
    tgt = _d.targets(_d.profile_of(db))
    hour = _d.hour_of(at) or datetime.now().hour
    return {"goal": tgt["goal"], "local_hour": f"{hour:02d}:00", "meal_hint": meal_hint(hour),
            "meals_count": sum(1 for m in meals if _d.counts(m)), "totals": t,
            "targets": {"calories": tgt["calories"], "protein_g": tgt["protein_g"]},
            "kcal_burned": None, "workouts": [],
            "remaining_kcal": max(0, round(tgt["calories"] - t["calories"])),
            "remaining_protein_g": max(0, round(tgt["protein_g"] - t["protein_g"]))}


def _a_coach_menu(action: str, p: dict) -> dict:
    db = _d.load()
    lang = _lang(db, p)
    names = [str(n) for n in (p.get("photos") or []) if isinstance(n, str)][:PHOTOS_MAX]
    paths = [_d.photo_path(n) for n in names]
    if not names or not all(paths):
        return {"ok": False, "error": "photo_not_found" if names else "no_photo", "hint": "1-5 photos of a menu"}
    at = _d.clean_when(p.get("at"), _d.now_local())
    ctx = day_context(db, at)
    extra = str(p.get("context_text") or "").strip()[:500]
    res = _d.estimate("menu_coach", {"day": ctx, "context_text": extra, "lang": lang, "photos_n": len(names),
                                     "images": [str(x) for x in paths]})
    text = res.get("out") if res.get("ok") else None
    if isinstance(text, dict):
        text = text.get("recommendation") or text.get("text")
    db["coach"] = {"asked_at": at, "photos": names, "context_text": extra or None,
                   "recommendation": str(text).strip()[:3000] if text else None,
                   "error": None if text else (res.get("error") or "estimator_bad_answer")}
    db["view"] = {**(db.get("view") or {}), "screen": "coach"}
    _d.save(db)
    return {"ok": bool(text), "error": db["coach"]["error"]}
