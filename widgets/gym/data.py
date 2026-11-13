"""Gym — guided sessions from a versioned plan, exercises, muscle recovery (V2-900, ported from the original app).

One person, one store (`widgets/_data/gym/state.json`): the original app's D1 tables become lists in it —
`gym_user_program` → `program`, `gym_program_version` → `versions` (every change of plan is a new version with its
reason; a session runs on the version's SNAPSHOT, never on the live file), `gym_session` → `sessions`, `gym_set` →
`sets`, `gym_event` → `events`, `pt_plan` → `plan`. The profile's gym columns become `equipment`, `preferences`, `age`.

The GUIDED session lives here too (`live`): the block, the set, the rest and the timer's end are stored, so every
screen shows the same session, the voice can drive it («done», «next», «skip it») and a reload resumes where it was.
The screen that claimed it (`claim`) reads the heart-rate strap, beeps and keeps the screen awake; any screen may
report a timer that ran out (`timer_done`, idempotent against the cursor it saw).

Handlers are in `actions.py` (a table). Stdlib only; nothing here raises to the caller.
"""
from __future__ import annotations

import logging
import os
import shutil
import time

from .. import store
from . import coach, muscles, program as prog

logger = logging.getLogger(__name__)

WID = "gym"
DB_VERSION = 1
SESSIONS_IN_VIEW = 60
SESSIONS_IN_REFS = 20
KCAL_PER_MIN = 6            # the original app's estimate for moderate strength work; shown as an estimate
HR_RECENT_S = 15
HR_EXTEND_BPM = 130         # rest ran out with the heart still above this → +30 s, once
HR_EXTEND_S = 30
EQUIPMENT = ("dumbbells", "barbells", "squat_rack", "adjustable_bench", "leg_machines", "cables", "cardio",
             "functional", "pullup_bar")
VIEWS = ("home", "preview", "session", "calendar", "muscles", "config", "planner", "program", "summary", "exercise",
         "log")
IMG_PREFIX = "ex-"


def _default() -> dict:
    return {"_v": DB_VERSION, "program": None, "versions": [], "equipment": {k: False for k in EQUIPMENT},
            "preferences": "", "age": None, "sessions": [], "sets": [], "events": [], "plan": [], "live": None,
            "view": {"name": "home", "n": 0}, "seq": 0}


def _migrate(db: dict, from_v: int) -> dict:
    return db


def _load() -> dict:
    db = store.load(WID, _default(), version=DB_VERSION, migrate=_migrate)
    for k, v in _default().items():
        db.setdefault(k, v)
    return db


def _save(db: dict) -> None:
    store.save(WID, db)


def _id(db: dict) -> int:
    db["seq"] = int(db.get("seq") or 0) + 1
    return db["seq"]


def _now() -> float:
    return time.time()


def _date(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def _today() -> str:
    return _date(_now())


# ── the plan the person runs: the snapshot of the current version ─────────────────────────────────────────────────

def _current_program(db: dict) -> dict | None:
    cur = db.get("program")
    if not cur:
        return None
    for v in db.get("versions") or []:
        if v.get("program_key") == cur.get("key") and v.get("version") == cur.get("version"):
            return v.get("snapshot")
    return prog.programs().get(cur.get("key"))


def _sessions_newest(db: dict) -> list:
    return sorted(db.get("sessions") or [], key=lambda s: (s.get("started_at") or 0, s.get("id") or 0), reverse=True)


def _plan_for(db: dict, date: str) -> dict | None:
    return next((p for p in db.get("plan") or [] if p.get("date") == date), None)


def _today_day(db: dict, p: dict) -> dict:
    nd = prog.next_day(p, _sessions_newest(db), _plan_for(db, _today()))
    key = nd["day_key"]
    blocks = prog.day_blocks(p, key)
    return {**nd, "day_name": ((p.get("days") or {}).get(key) or {}).get("name") or key,
            "last_name": ((p.get("days") or {}).get(nd["last"]) or {}).get("name") if nd["last"] else None,
            "blocks": blocks, "estimated_min": prog.estimate_minutes(blocks),
            "exercise_count": sum(1 for b in blocks if b.get("type") == "exercise")}


def _last_weights(db: dict) -> dict:
    out: dict = {}
    for s in sorted(db.get("sets") or [], key=lambda x: x.get("id") or 0):
        if s.get("exercise_key") and s.get("weight_kg") is not None:
            out[s["exercise_key"]] = {"weight_kg": s["weight_kg"], "at": s.get("completed_at")}
    return out


# ── a recorded session as the card and the brain read it ──────────────────────────────────────────────────────────

def _groups(sets: list) -> list:
    """Sets grouped per exercise in order of completion, labelled E1, E1.1… (the original app's summarySetsByExercise)."""
    ordered = sorted(sets, key=lambda s: (s.get("completed_at") or 0, s.get("set_index") or 0, s.get("id") or 0))
    seen, groups = {}, []
    for s in ordered:
        k = s.get("exercise_key") or s.get("exercise_name") or "?"
        if k not in seen:
            seen[k] = len(groups)
            groups.append({"label": f"E{len(groups) + 1}", "key": s.get("exercise_key"),
                           "name": prog.exercise_name(s.get("exercise_key"), s.get("exercise_name") or k), "sets": []})
        g = groups[seen[k]]
        g["sets"].append({"id": s.get("id"), "label": f"{g['label']}.{len(g['sets']) + 1}", "reps": s.get("reps_done"),
                          "weight_kg": s.get("weight_kg"), "rir": s.get("rir")})
    return groups


def _session_view(db: dict, s: dict, p: dict | None, sets_by: dict) -> dict:
    sets = sets_by.get(s.get("id"), [])
    end = s.get("ended_at") or (_now() if s.get("status") == "active" else None)
    dur = max(0, int(end - s["started_at"])) if end and s.get("started_at") else None
    day_name = ((p or {}).get("days") or {}).get(s.get("day_key"), {}).get("name") if p else None
    return {"id": s.get("id"), "date": _date(s.get("started_at") or 0), "day_key": s.get("day_key"),
            "day_name": day_name or s.get("day_key"), "status": s.get("status"), "source": s.get("source"),
            "started_at": int((s.get("started_at") or 0) * 1000), "ended_at": int(end * 1000) if s.get("ended_at") else None,
            "duration_s": dur, "kcal": round(dur / 60 * KCAL_PER_MIN) if dur else None,
            "volume_kg": round(sum((x.get("reps_done") or 0) * (x.get("weight_kg") or 0) for x in sets)),
            "sets_count": len(sets), "exercises_count": len({x.get("exercise_key") or x.get("exercise_name") for x in sets}),
            "version": s.get("version"), "notes": s.get("notes") or "", "hr_avg": s.get("hr_avg"), "hr_max": s.get("hr_max"),
            "exercises": _groups(sets)}


def _live_view(db: dict, p: dict | None) -> dict | None:
    lv = db.get("live")
    if not lv:
        return None
    blocks = lv.get("blocks") or []
    i = int(lv.get("i") or 0)
    block = blocks[i] if 0 <= i < len(blocks) else None
    sess = next((s for s in db.get("sessions") or [] if s.get("id") == lv.get("session_id")), {})
    sets = [x for x in db.get("sets") or [] if x.get("session_id") == lv.get("session_id")]
    hr = lv.get("hr") or {}
    hr_now = hr.get("bpm") if hr and _now() - float(hr.get("at") or 0) <= HR_RECENT_S else None
    lw = _last_weights(db)
    return {"session_id": lv.get("session_id"), "rev": lv.get("rev", 0), "day_key": lv.get("day_key"),
            "day_name": ((p or {}).get("days") or {}).get(lv.get("day_key"), {}).get("name") or lv.get("day_key"),
            "started_at": int(float(lv.get("started_at") or 0) * 1000),
            "stale": _date(float(lv.get("started_at") or 0)) != _today(),
            "blocks": blocks, "i": i, "total": len(blocks), "block": block, "finished": block is None,
            "progress": 100 if block is None else round(i / max(1, len(blocks)) * 100),
            "set": int(lv.get("set") or 0), "resting": bool(lv.get("resting")), "timer": lv.get("timer"),
            "weight": lv.get("weight"), "reps": lv.get("reps"), "rir": lv.get("rir"),
            "last_weight": (lw.get((block or {}).get("key") or "") or {}).get("weight_kg") if block else None,
            "owner": lv.get("owner"), "cue": lv.get("cue", 0), "cue_kind": lv.get("cue_kind", "tick"),
            "note": lv.get("note"), "alt": lv.get("alt"), "heart_rate": hr_now, "sets": _groups(sets),
            "sets_count": len(sets), "version": sess.get("version")}


def _images() -> dict:
    """{key: url} for the exercises with a vendored picture. The pictures ship in `img/`; the engine serves an app's
    files only from its data directory (`/widgets/gym/asset/<name>`), so they are copied there once."""
    try:
        src, dst = os.path.join(os.path.dirname(__file__), "img"), store.data_dir(WID)
        have = set(os.listdir(dst))
        out = {}
        for key, e in prog.exercises().items():
            f = e.get("image") or ""
            if not f:
                continue
            name = IMG_PREFIX + f
            if name not in have and os.path.isfile(os.path.join(src, f)):
                shutil.copyfile(os.path.join(src, f), os.path.join(dst, name))
                have.add(name)
            if name in have:
                out[key] = f"/widgets/{WID}/asset/{name}"
        return out
    except Exception as e:  # noqa: BLE001 — no pictures is a card without pictures, never a broken one
        logger.debug(f"gym: images unavailable ({e!r})")
        return {}


def view_data(q: str = "") -> dict:
    try:
        db = _load()
        p = _current_program(db)
        status = "session" if db.get("live") else ("ready" if p else "onboarding")
        sets_by: dict = {}
        for x in db.get("sets") or []:
            sets_by.setdefault(x.get("session_id"), []).append(x)
        newest = _sessions_newest(db)
        done_count = sum(1 for s in newest if s.get("status") == "done")
        out = {
            "status": status, "now": int(_now() * 1000), "today": _today(),
            "view": (db.get("view") or {}).get("name") or "home", "view_n": (db.get("view") or {}).get("n", 0),
            "view_arg": (db.get("view") or {}).get("arg"),
            "programs": prog.catalogue(),
            "equipment": {k: bool((db.get("equipment") or {}).get(k)) for k in EQUIPMENT},
            "preferences": db.get("preferences") or "", "age": db.get("age"),
            "plan": sorted(db.get("plan") or [], key=lambda x: x.get("date") or ""),
            "coach": {"available": coach.available()},
            "sessions": [_session_view(db, s, p, sets_by) for s in newest[:SESSIONS_IN_VIEW]],
            "sessions_total": len(newest),
            "muscles": muscles.compute_muscle_state(db.get("sets") or []),
            "last_weights": _last_weights(db),
            "exercises": {k: {"name": e.get("name")} for k, e in prog.exercises().items()},
            "images": _images(),
            "program": None, "next": None, "live": None,
        }
        if p:
            cur = db["program"]
            out["program"] = {
                "key": p.get("key"), "name": p.get("name"), "summary": p.get("summary"), "level": p.get("level"),
                "schedule": p.get("schedule") or [], "phases": p.get("phases") or [],
                "day_names": {k: d.get("name") for k, d in (p.get("days") or {}).items()},
                "version": cur.get("version"), "day_index": cur.get("day_index", 0),
                "started_at": int(float(cur.get("started_at") or 0) * 1000),
                "versions": [{"version": v.get("version"), "reason": v.get("reason"), "at": int(float(v.get("at") or 0) * 1000)}
                             for v in db.get("versions") or [] if v.get("program_key") == p.get("key")],
                "phase": prog.phase_of(p, done_count), "done_count": done_count}
            out["next"] = _today_day(db, p)
            out["live"] = _live_view(db, p)
        elif db.get("live"):
            out["live"] = _live_view(db, None)
        return out
    except Exception as e:  # noqa: BLE001 — a broken store is an empty card that says so, never a dead turn
        logger.warning(f"gym: view_data failed: {e!r}")
        return {"status": "onboarding", "programs": prog.catalogue(), "sessions": [], "muscles": [], "error": str(e)[:120]}


def ref_index() -> list[dict]:
    """The recorded sessions the voice can name («delete Tuesday's workout», «the legs session»)."""
    try:
        db = _load()
        p = _current_program(db)
        out = []
        for s in _sessions_newest(db)[:SESSIONS_IN_REFS]:
            name = prog.en(((p or {}).get("days") or {}).get(s.get("day_key"), {}).get("name")) or s.get("day_key") or ""
            out.append({"id": str(s.get("id")), "label": f"{name} {_date(s.get('started_at') or 0)}".strip(),
                        "field": "sessionId", "hint": s.get("status")})
        return out
    except Exception:  # noqa: BLE001
        return []


def prompt_digest() -> str:
    """With the card open: the live session (block, set, rest, heart rate) or today's day — no round trip needed."""
    try:
        v = view_data()
        lv = v.get("live")
        if lv:
            b = lv.get("block")
            if not b:
                return "Gym session on screen: all blocks done — `finish` saves it."
            bits = [f"{prog.en(lv.get('day_name'))}, block {lv['i'] + 1}/{lv['total']}"]
            name = prog.en(prog.block_name(b))
            if b.get("type") == "exercise":
                bits.append(f"{name} set {lv['set'] + 1} of {b.get('sets') or 1}, target {prog.en(b.get('reps'))} reps")
                if lv.get("weight") is not None:
                    bits.append(f"weight on screen {lv['weight']} kg")
                if lv.get("last_weight") is not None:
                    bits.append(f"last time {lv['last_weight']} kg")
            else:
                bits.append(f"{b.get('type')} «{name or b.get('type')}»")
            t = lv.get("timer")
            if t:
                left = t.get("left") if t.get("paused") else max(0, round((t.get("ends_at", 0) - v["now"]) / 1000))
                bits.append(("resting, " if lv.get("resting") else "") + f"{left} s left" + (" (paused)" if t.get("paused") else ""))
            bits.append(f"heart rate {lv['heart_rate']} bpm" if lv.get("heart_rate") is not None else "no heart-rate reading")
            return "Gym session on screen: " + "; ".join(bits) + "."
        n = v.get("next")
        if n:
            last = v["sessions"][0] if v.get("sessions") else None
            s = (f"Gym: today's day is {prog.en(n['day_name'])} (~{n['estimated_min']} min, {n['exercise_count']} exercises)")
            if last:
                s += f"; last session {prog.en(last['day_name'])} on {last['date']} ({last['status']})"
            return s + "."
        return "Gym: no program chosen yet."
    except Exception as e:  # noqa: BLE001 — a broken digest leaves the turn without the figures, never broken
        logger.warning(f"gym: prompt_digest failed: {e}")
        return ""


from .setup import _a_select_program, _a_configure, _a_open_view  # noqa: E402 — handlers read `data` through `_d`
from .actions import (  # noqa: E402
    _a_start_session, _a_set_values, _a_set_done, _a_next,
    _a_undo_set, _a_skip_exercise, _a_pause_timer, _a_resume_timer, _a_adjust_rest, _a_claim, _a_timer_done, _a_hr)
from .records import (  # noqa: E402
    _a_suggest_alternative, _a_use_alternative, _a_close_alternatives, _a_end_early, _a_finish, _a_abort,
    _a_delete_session, _a_delete_day, _a_log_workout, _a_edit_session, _a_adjust_today, _a_refresh_plan)

ACTIONS = {
    "select_program": _a_select_program,
    "configure": _a_configure,
    "open_view": _a_open_view,
    "start_session": _a_start_session,
    "set_values": _a_set_values,
    "set_done": _a_set_done,
    "next": _a_next,
    "undo_set": _a_undo_set,
    "skip_exercise": _a_skip_exercise,
    "pause_timer": _a_pause_timer,
    "resume_timer": _a_resume_timer,
    "adjust_rest": _a_adjust_rest,
    "suggest_alternative": _a_suggest_alternative,
    "use_alternative": _a_use_alternative,
    "close_alternatives": _a_close_alternatives,
    "end_early": _a_end_early,
    "finish": _a_finish,
    "abort": _a_abort,
    "delete_session": _a_delete_session,
    "delete_day": _a_delete_day,
    "log_workout": _a_log_workout,
    "edit_session": _a_edit_session,
    "adjust_today": _a_adjust_today,
    "refresh_plan": _a_refresh_plan,
    "claim": _a_claim,
    "timer_done": _a_timer_done,
    "hr": _a_hr,
}


def apply_action(action: str, payload: dict = None) -> dict:
    handler = ACTIONS.get(action) if isinstance(action, str) else None
    if handler is None:
        return {"ok": False, "error": "unknown_action", "action": action}
    try:
        return handler(action, payload if isinstance(payload, dict) else {})
    except Exception as e:  # noqa: BLE001 — a failing action answers why, never a dead turn
        logger.warning(f"gym: {action} failed: {e!r}")
        return {"ok": False, "error": str(e)[:160]}
