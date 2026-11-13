"""What each gym action does, one function per action; `data.ACTIONS` maps the names to them (V2-900).

The guided session is the original app's client logic (`_enterBlock`, `markSetDone`, `_tickTimer`, `undoLastSet`,
`skipExercise`) moved here so the session is the same on every screen and the
voice can drive it. Every module-level name of `data` is read through `_d`.
"""
from __future__ import annotations

from . import coach
from . import data as _d
from . import program as prog

TIMER_GRACE_S = 1.5          # a screen's «the timer ran out» a little early (clock skew) still counts


# ── the live session's cursor ─────────────────────────────────────────────────────────────────────────────────────

def _bump(lv: dict, cue: str | None = None) -> None:
    lv["rev"] = int(lv.get("rev") or 0) + 1
    if cue:
        lv["cue"] = int(lv.get("cue") or 0) + 1
        lv["cue_kind"] = cue


def _start_timer(lv: dict, secs: int) -> None:
    secs = max(1, int(secs))
    lv["timer"] = {"ends_at": int((_d._now() + secs) * 1000), "left": secs, "total": secs, "paused": False}


def _enter_block(db: dict, lv: dict, i: int) -> None:
    """the original app's _enterBlock: weight from the LAST real weight of this exercise, else the program's suggestion; a
    timed block starts its timer at once, an exercise waits for «done»."""
    blocks = lv.get("blocks") or []
    lv.update({"i": i, "set": 0, "resting": False, "rest_extended": False, "timer": None, "note": None, "alt": None})
    if i >= len(blocks):
        lv["i"] = len(blocks)
        lv["weight"], lv["reps"], lv["rir"] = None, None, None
        _bump(lv, "end")
        return
    b = blocks[i]
    last = (_d._last_weights(db).get(b.get("key") or "") or {}).get("weight_kg") if b.get("key") else None
    lv["weight"] = last if last is not None else b.get("weight_initial_kg")
    lv["reps"] = prog.default_reps(b)
    lv["rir"] = None
    if b.get("type") != "exercise":
        _start_timer(lv, b.get("duration_sec") or 30)
    _bump(lv, "tick")


def _live(db: dict) -> dict | None:
    return db.get("live")


def _no_live() -> dict:
    return {"ok": False, "error": "no_session", "hint": "start_session starts today's workout"}


def _session(db: dict, sid) -> dict | None:
    try:
        sid = int(sid)
    except (TypeError, ValueError):
        return None
    return next((s for s in db.get("sessions") or [] if s.get("id") == sid), None)


def _event(db: dict, sid, i, kind: str, payload: dict) -> None:
    db["events"].append({"id": _d._id(db), "session_id": sid, "block_index": i, "type": kind, "payload": payload,
                         "at": _d._now()})


def _num(v, lo=None, hi=None):
    try:
        x = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None
    if (lo is not None and x < lo) or (hi is not None and x > hi):
        return None
    return int(x) if x == int(x) else round(x, 2)


def _end(db: dict, status: str, notes: str = "") -> dict:
    """Close the live session as done or partial; the program moves to its next day (the original app always advanced)."""
    lv = _live(db)
    s = _session(db, lv.get("session_id")) if lv else None
    if s:
        s.update({"status": status, "ended_at": _d._now(), "notes": notes or s.get("notes") or ""})
        if lv.get("hr_n"):
            s["hr_avg"], s["hr_max"] = round(lv["hr_sum"] / lv["hr_n"]), lv.get("hr_max")
    if db.get("program"):
        db["program"]["day_index"] = int(db["program"].get("day_index") or 0) + 1
    db["live"] = None
    db["view"] = {"name": "home", "n": int((db.get("view") or {}).get("n") or 0) + 1}
    _refresh_plan_silently(db)
    _d._save(db)
    return {"ok": True, "status": status, "session": s.get("id") if s else None}


def _refresh_plan_silently(db: dict) -> None:
    """the original app recomputed the trainer's plan after every change; here the seam answers or nothing changes."""
    r = coach.ask("plan", {})
    if r.get("ok") and isinstance(r.get("json"), list):
        db["plan"] = [x for x in r["json"] if isinstance(x, dict) and x.get("date") and x.get("type") in ("gym", "cardio", "rest")]


# ── the guided session ────────────────────────────────────────────────────────────────────────────────────────────

def _a_start_session(action: str, p: dict) -> dict:
    db = _d._load()
    if _live(db):
        return {"ok": True, "resumed": True, "session": db["live"].get("session_id")}
    pr = _d._current_program(db)
    if not pr:
        return {"ok": False, "error": "no_program", "hint": "select_program first", "programs": sorted(prog.programs())}
    day = str(p.get("day") or "").strip().lower()
    if day and day not in (pr.get("days") or {}):
        return {"ok": False, "error": "unknown_day", "days": sorted(pr.get("days") or {})}
    nd = _d._today_day(db, pr)
    key = day or nd["day_key"]
    blocks = p.get("blocks") if isinstance(p.get("blocks"), list) and p.get("blocks") else prog.day_blocks(pr, key)
    sid = _d._id(db)
    db["sessions"].append({"id": sid, "program_key": pr.get("key"), "version": (db.get("program") or {}).get("version"),
                           "day_key": key, "day_index": (db.get("program") or {}).get("day_index", 0),
                           "started_at": _d._now(), "ended_at": None, "status": "active", "notes": "", "source": "guided"})
    lv = {"session_id": sid, "day_key": key, "blocks": blocks, "started_at": _d._now(), "owner": None, "rev": 0,
          "cue": 0, "cue_kind": "tick", "hr": None, "hr_sum": 0, "hr_n": 0, "hr_max": None, "rejected": {}}
    db["live"] = lv
    _enter_block(db, lv, 0)
    db["view"] = {"name": "session", "n": int((db.get("view") or {}).get("n") or 0) + 1}
    _d._save(db)
    return {"ok": True, "session": sid, "day": key, "blocks": len(blocks)}


def _a_set_values(action: str, p: dict) -> dict:
    db = _d._load()
    lv = _live(db)
    if not lv:
        return _no_live()
    got = {}
    for k, lo, hi in (("weight_kg", 0, 1000), ("reps", 0, 1000), ("rir", 0, 10)):
        if k in p:
            v = _num(p.get(k), lo, hi)
            if v is None and p.get(k) is not None:
                return {"ok": False, "error": f"bad_{k}"}
            got[k] = v
    if "weight_delta" in p:
        d = _num(p.get("weight_delta"), -100, 100) or 0
        got["weight_kg"] = max(0, round((float(lv.get("weight") or 0)) + d, 2))
    if "reps_delta" in p:
        d = _num(p.get("reps_delta"), -100, 100) or 0
        got["reps"] = max(0, int((lv.get("reps") or 0) + d))
    if not got:
        return {"ok": False, "error": "nothing_to_change", "fields": ["weight_kg", "reps", "rir"]}
    if "weight_kg" in got:
        lv["weight"] = got["weight_kg"]
    if "reps" in got:
        lv["reps"] = int(got["reps"]) if got["reps"] is not None else None
    if "rir" in got:
        lv["rir"] = got["rir"]
    _bump(lv)
    _d._save(db)
    return {"ok": True, "weight_kg": lv.get("weight"), "reps": lv.get("reps"), "rir": lv.get("rir")}


def _a_set_done(action: str, p: dict) -> dict:
    """the original app's markSetDone: the set is saved with what is on screen (or what he said), then rest or the next block."""
    db = _d._load()
    lv = _live(db)
    if not lv:
        return _no_live()
    blocks, i = lv.get("blocks") or [], int(lv.get("i") or 0)
    if i >= len(blocks) or blocks[i].get("type") != "exercise":
        return {"ok": False, "error": "not_an_exercise", "hint": "`next` moves on from a timed block"}
    if lv.get("resting"):
        return {"ok": False, "error": "resting", "hint": "`next` ends the rest"}
    if "i" in p and _num(p.get("i")) is not None and int(_num(p["i"])) != i:   # the card saw another block
        return {"ok": False, "error": "stale", "i": i}
    b = blocks[i]
    weight = _num(p["weight_kg"], 0, 1000) if "weight_kg" in p else lv.get("weight")
    reps = _num(p["reps"], 0, 1000) if "reps" in p else lv.get("reps")
    rir = _num(p["rir"], 0, 10) if "rir" in p else lv.get("rir")
    set_index = int(lv.get("set") or 0)
    db["sets"].append({"id": _d._id(db), "session_id": lv["session_id"], "exercise_key": b.get("key"),
                       "exercise_name": prog.en(prog.block_name(b)), "muscle_key": b.get("muscle_key"),
                       "set_index": set_index, "reps_target": prog.en(b.get("reps")),
                       "reps_done": int(reps) if reps is not None else None, "weight_kg": weight, "rir": rir,
                       "completed_at": _d._now()})
    lv["weight"], lv["reps"] = weight, int(reps) if reps is not None else lv.get("reps")
    total = int(b.get("sets") or 1)
    if set_index + 1 >= total:
        _enter_block(db, lv, i + 1)
    else:
        lv["set"] = set_index + 1
        lv["resting"], lv["rest_extended"], lv["note"] = True, False, None
        _start_timer(lv, b.get("rest_sec") or 60)
        _bump(lv, "tick")
    _d._save(db)
    return {"ok": True, "saved": {"set": set_index + 1, "of": total, "reps": reps, "weight_kg": weight},
            "resting": bool(lv.get("resting")), "block": lv.get("i")}


def _end_rest(lv: dict) -> None:
    lv["resting"], lv["timer"], lv["note"] = False, None, None
    _bump(lv, "tick")


def _a_next(action: str, p: dict) -> dict:
    """«Start now»: ends the rest, or leaves a timed block (stretch, cardio, transition) for the next one."""
    db = _d._load()
    lv = _live(db)
    if not lv:
        return _no_live()
    blocks, i = lv.get("blocks") or [], int(lv.get("i") or 0)
    if lv.get("resting"):
        _end_rest(lv)
    elif i < len(blocks) and blocks[i].get("type") != "exercise":
        _enter_block(db, lv, i + 1)
    elif i < len(blocks):
        return {"ok": False, "error": "exercise_in_progress",
                "hint": "`set_done` records the set; `skip_exercise` leaves the exercise"}
    else:
        return {"ok": False, "error": "finished", "hint": "`finish` saves the session"}
    _d._save(db)
    return {"ok": True, "block": lv.get("i"), "resting": bool(lv.get("resting"))}


def _a_undo_set(action: str, p: dict) -> dict:
    """the original app's undoLastSet: the last set goes, and the session goes back to that exercise and set."""
    db = _d._load()
    lv = _live(db)
    if not lv:
        return _no_live()
    mine = [s for s in db["sets"] if s.get("session_id") == lv["session_id"]]
    if not mine:
        return {"ok": False, "error": "nothing_to_undo"}
    last = max(mine, key=lambda s: s.get("id") or 0)
    db["sets"] = [s for s in db["sets"] if s is not last]
    k = last.get("exercise_key") or last.get("exercise_name")
    done = sum(1 for s in db["sets"] if s.get("session_id") == lv["session_id"]
               and (s.get("exercise_key") or s.get("exercise_name")) == k)
    target = next((j for j, b in enumerate(lv.get("blocks") or [])
                   if b.get("type") == "exercise" and (b.get("key") or prog.en(prog.block_name(b))) == k), -1)
    if target >= 0:
        _enter_block(db, lv, target)
        lv["set"] = done
        lv["weight"], lv["reps"] = last.get("weight_kg"), last.get("reps_done")
    _bump(lv)
    _d._save(db)
    return {"ok": True, "undone": {"exercise": last.get("exercise_name"), "reps": last.get("reps_done"),
                                   "weight_kg": last.get("weight_kg")}}


def _a_skip_exercise(action: str, p: dict) -> dict:
    db = _d._load()
    lv = _live(db)
    if not lv:
        return _no_live()
    blocks, i = lv.get("blocks") or [], int(lv.get("i") or 0)
    if i >= len(blocks):
        return {"ok": False, "error": "finished"}
    b = blocks[i]
    _event(db, lv["session_id"], i, "skipped", {"name": prog.en(prog.block_name(b)), "exercise_key": b.get("key"),
                                                 "sets_done": lv.get("set", 0), "sets_target": b.get("sets")})
    _enter_block(db, lv, i + 1)
    _d._save(db)
    return {"ok": True, "skipped": prog.en(prog.block_name(b)) or b.get("type"), "block": lv.get("i")}


def _a_pause_timer(action: str, p: dict) -> dict:
    db = _d._load()
    lv = _live(db)
    t = (lv or {}).get("timer")
    if not t:
        return {"ok": False, "error": "no_timer"} if lv else _no_live()
    if not t.get("paused"):
        t["left"] = max(0, round((t["ends_at"] - _d._now() * 1000) / 1000))
        t["paused"] = True
        _bump(lv)
        _d._save(db)
    return {"ok": True, "paused": True, "left": t["left"]}


def _a_resume_timer(action: str, p: dict) -> dict:
    db = _d._load()
    lv = _live(db)
    t = (lv or {}).get("timer")
    if not t:
        return {"ok": False, "error": "no_timer"} if lv else _no_live()
    if t.get("paused"):
        t["ends_at"] = int((_d._now() + int(t.get("left") or 0)) * 1000)
        t["paused"] = False
        _bump(lv)
        _d._save(db)
    return {"ok": True, "paused": False}


def _a_adjust_rest(action: str, p: dict) -> dict:
    """±seconds on the running timer (the original app's −15 s / +15 s)."""
    db = _d._load()
    lv = _live(db)
    t = (lv or {}).get("timer")
    if not t:
        return {"ok": False, "error": "no_timer"} if lv else _no_live()
    d = _num(p.get("seconds"), -3600, 3600)
    if d is None:
        return {"ok": False, "error": "bad_seconds"}
    if t.get("paused"):
        t["left"] = max(0, int(t.get("left") or 0) + int(d))
    else:
        left = max(0, round((t["ends_at"] - _d._now() * 1000) / 1000) + int(d))
        t["ends_at"], t["left"] = int((_d._now() + left) * 1000), left
    _bump(lv)
    _d._save(db)
    return {"ok": True, "left": t.get("left")}


def _a_timer_done(action: str, p: dict) -> dict:
    """A screen saw the timer reach zero. Counted once, only against the cursor that screen saw. A rest that ends
    with the heart still above 130 bpm gets 30 s more, once (the original app's dynamic rest)."""
    db = _d._load()
    lv = _live(db)
    if not lv:
        return _no_live()
    t = lv.get("timer")
    seen = (_num(p.get("i")), _num(p.get("set")), bool(p.get("resting")))
    if not t or t.get("paused") or seen != (lv.get("i"), lv.get("set"), bool(lv.get("resting"))) \
            or t["ends_at"] > (_d._now() + TIMER_GRACE_S) * 1000:
        return {"ok": True, "ignored": True}
    hr = lv.get("hr") or {}
    if lv.get("resting") and not lv.get("rest_extended") and hr.get("bpm") and hr["bpm"] > _d.HR_EXTEND_BPM \
            and _d._now() - float(hr.get("at") or 0) <= _d.HR_RECENT_S:
        lv["rest_extended"] = True
        _start_timer(lv, _d.HR_EXTEND_S)
        lv["note"] = {"kind": "rest_extended", "bpm": hr["bpm"], "seconds": _d.HR_EXTEND_S}
        _bump(lv, "tick")
    elif lv.get("resting"):
        _end_rest(lv)
        lv["cue_kind"] = "end"
    else:
        _enter_block(db, lv, int(lv.get("i") or 0) + 1)
        lv["cue_kind"] = "end"
    _d._save(db)
    return {"ok": True, "block": lv.get("i"), "resting": bool(lv.get("resting"))}


# ── the screen that drives the session: heart rate, beeps, wake lock ─────────────────────────────────────────────

def _a_claim(action: str, p: dict) -> dict:
    db = _d._load()
    lv = _live(db)
    owner = str(p.get("owner") or "")[:64]
    if not lv or not owner:
        return {"ok": False, "error": "no_session" if not lv else "owner is required"}
    if lv.get("owner") and lv["owner"] != owner and not p.get("force"):
        return {"ok": False, "owned_by_another_screen": True}
    if lv.get("owner") != owner:
        lv["owner"] = owner
        _bump(lv)
        _d._save(db)
    return {"ok": True, "owner": owner}


def _a_hr(action: str, p: dict) -> dict:
    db = _d._load()
    lv = _live(db)
    if not lv:
        return _no_live()
    if lv.get("owner") != str(p.get("owner") or ""):
        return {"ok": False, "owned_by_another_screen": True}
    bpm = _num(p.get("bpm"), 20, 250)
    if bpm is None:
        return {"ok": False, "error": "bad_bpm"}
    lv["hr"] = {"bpm": int(bpm), "at": _d._now()}
    lv["hr_sum"] = (lv.get("hr_sum") or 0) + int(bpm)
    lv["hr_n"] = (lv.get("hr_n") or 0) + 1
    lv["hr_max"] = max(int(bpm), lv.get("hr_max") or 0)
    _d._save(db)
    return {"ok": True}
