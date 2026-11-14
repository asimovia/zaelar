"""The gym's actions on records: alternatives, ending a session, deleting, a workout told and a workout corrected
(V2-900). Split from `actions.py` (the session's cursor) for size only; `data.ACTIONS` maps the names here too.
Every module-level name of `data` is read through `_d`, the shared helpers through `_a`.
"""
from __future__ import annotations

import re
import time
import unicodedata

from . import actions as _a
from . import coach
from . import data as _d
from . import program as prog

MAX_ALT_REJECTED = 20
_live, _no_live, _session, _event, _num, _bump = _a._live, _a._no_live, _a._session, _a._event, _a._num, _a._bump
_enter_block, _end, _refresh_plan_silently = _a._enter_block, _a._end, _a._refresh_plan_silently


# ── alternatives: the app's own list first, then the model when it exists ───────────────────────────────────────

def _offer(lv: dict, i: int) -> None:
    blocks = lv.get("blocks") or []
    b = blocks[i]
    rejected = (lv.get("rejected") or {}).get(str(i), [])
    cur_name = prog.en(prog.block_name(b))
    pool = [a for a in prog.alternatives_for(b)
            if prog.en(a.get("name")) not in rejected and prog.en(a.get("name")) != cur_name and a.get("key") != b.get("key")]
    alt = pool[0] if pool else None
    source = "catalogue"
    if alt is None:
        r = coach.ask("alternative", {"name": cur_name, "sets": b.get("sets"), "reps": prog.en(b.get("reps")),
                                      "weight": b.get("weight_initial_kg"), "block_type": b.get("type"),
                                      "rejected": ", ".join(rejected) or "none"})
        if r.get("ok") and isinstance(r.get("json"), dict) and r["json"].get("name"):
            alt, source = r["json"], "model"
    lv["alt"] = {"i": i, "current": alt, "source": source if alt else None, "rejected": rejected,
                 "exhausted": alt is None, "model": coach.available()}


def _a_suggest_alternative(action: str, p: dict) -> dict:
    """Show a substitute for the current block; asked again, the one on screen counts as rejected and the next shows."""
    db = _d._load()
    lv = _live(db)
    if not lv:
        return _no_live()
    blocks, i = lv.get("blocks") or [], int(lv.get("i") or 0)
    if i >= len(blocks):
        return {"ok": False, "error": "finished"}
    alt = lv.get("alt")
    if alt and alt.get("i") == i and alt.get("current"):
        rej = lv.setdefault("rejected", {}).setdefault(str(i), [])
        rej.append(prog.en(alt["current"].get("name")))
        del rej[:-MAX_ALT_REJECTED]
    _offer(lv, i)
    _bump(lv)
    _d._save(db)
    cur = lv["alt"]["current"]
    return {"ok": True, "alternative": prog.en(cur.get("name")) if cur else None, "exhausted": lv["alt"]["exhausted"]}


def _a_use_alternative(action: str, p: dict) -> dict:
    """The block on screen becomes the alternative shown (its type kept); the program's exercise stays its muscle
    reference, so the recovery map still credits the right muscles."""
    db = _d._load()
    lv = _live(db)
    if not lv:
        return _no_live()
    alt = lv.get("alt") or {}
    i = int(lv.get("i") or 0)
    if alt.get("i") != i or not alt.get("current"):
        return {"ok": False, "error": "no_alternative_shown", "hint": "suggest_alternative first"}
    original = lv["blocks"][i]
    new = {**original, **{k: v for k, v in alt["current"].items() if k != "why"}, "type": original.get("type")}
    if original.get("type") == "exercise":
        new["muscle_key"] = original.get("muscle_key") or original.get("key")
        if not alt["current"].get("key"):
            new.pop("key", None)
    _event(db, lv["session_id"], i, "alternative", {"from": prog.en(prog.block_name(original)),
                                                    "to": prog.en(new.get("name")), "exercise_key": original.get("key"),
                                                    "rejected": alt.get("rejected") or []})
    lv["blocks"][i] = new
    _enter_block(db, lv, i)
    _d._save(db)
    return {"ok": True, "now": prog.en(prog.block_name(new))}


def _a_close_alternatives(action: str, p: dict) -> dict:
    db = _d._load()
    lv = _live(db)
    if not lv:
        return _no_live()
    lv["alt"] = None
    _bump(lv)
    _d._save(db)
    return {"ok": True}


# ── ending ────────────────────────────────────────────────────────────────────────────────────────────────────────

def _a_end_early(action: str, p: dict) -> dict:
    db = _d._load()
    if not _live(db):
        return _no_live()
    return _end(db, "partial", str(p.get("notes") or "ended early")[:200])


def _a_finish(action: str, p: dict) -> dict:
    db = _d._load()
    if not _live(db):
        return _no_live()
    return _end(db, "done", str(p.get("notes") or "")[:200])


def _drop_sessions(db: dict, ids: set) -> None:
    db["sessions"] = [s for s in db["sessions"] if s.get("id") not in ids]
    db["sets"] = [s for s in db["sets"] if s.get("session_id") not in ids]
    db["events"] = [e for e in db["events"] if e.get("session_id") not in ids]


def _a_abort(action: str, p: dict) -> dict:
    """Discard the whole live session and its sets (the original app's abort)."""
    db = _d._load()
    lv = _live(db)
    if not lv:
        return _no_live()
    _drop_sessions(db, {lv.get("session_id")})
    db["live"] = None
    db["view"] = {"name": "home", "n": int((db.get("view") or {}).get("n") or 0) + 1}
    _d._save(db)
    return {"ok": True, "discarded": lv.get("session_id")}


def _a_delete_session(action: str, p: dict) -> dict:
    db = _d._load()
    s = _session(db, p.get("sessionId") or p.get("session"))
    if not s:
        return {"ok": False, "error": "session_not_found"}
    if _live(db) and db["live"].get("session_id") == s["id"]:
        return {"ok": False, "error": "session_is_live", "hint": "abort discards the live session"}
    _drop_sessions(db, {s["id"]})
    _d._save(db)
    return {"ok": True, "deleted": s["id"]}


def _a_delete_day(action: str, p: dict) -> dict:
    date = str(p.get("date") or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        return {"ok": False, "error": "date YYYY-MM-DD required"}
    db = _d._load()
    live_id = (db.get("live") or {}).get("session_id")
    ids = {s["id"] for s in db["sessions"] if _d._date(s.get("started_at") or 0) == date and s["id"] != live_id}
    _drop_sessions(db, ids)
    _d._save(db)
    return {"ok": True, "deleted": len(ids)}


# ── a workout told, a workout changed — structured by the agent, or by the model seam from a sentence ─────────────

def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(s or "").lower()) if unicodedata.category(c) != "Mn").strip()


def _key_for(name: str, key=None) -> str:
    if key and str(key).strip():
        return str(key).strip()[:60]
    f = _fold(name)
    for k, e in prog.exercises().items():
        n = e.get("name") or {}
        if f in (_fold(n.get("en")), _fold(n.get("es"))) if isinstance(n, dict) else f == _fold(n):
            return k
    return re.sub(r"[^a-z0-9]+", "-", f).strip("-")[:60] or "exercise"


def _sets_of(ex: dict) -> list:
    sets = ex.get("sets")
    if isinstance(sets, list):
        out = []
        for s in sets:
            if isinstance(s, dict):
                out.append({"reps": _num(s.get("reps"), 0, 1000), "weight_kg": _num(s.get("weight_kg"), 0, 1000),
                            "rir": _num(s.get("rir"), 0, 10)})
        return [s for s in out if s["reps"] is not None or s["weight_kg"] is not None]
    n = _num(sets, 1, 50)                    # the short form: {"sets": 4, "reps": 10, "weight_kg": 20}
    if n is None:
        return []
    return [{"reps": _num(ex.get("reps"), 0, 1000), "weight_kg": _num(ex.get("weight_kg"), 0, 1000), "rir": None}
            for _ in range(int(n))]


def _a_log_workout(action: str, p: dict) -> dict:
    """A workout done elsewhere: exercises with their sets. From a sentence (`text`) only through the model seam."""
    exercises = p.get("exercises")
    if not isinstance(exercises, list) or not exercises:
        if str(p.get("text") or "").strip():
            r = coach.ask("log_workout", {"text": str(p["text"])[:2000]})
            if not r.get("ok"):
                return {**r, "hint": "say the exercises with their sets: log_workout {exercises:[{name, sets, reps, weight_kg}]}"}
            j = r.get("json") or {}
            exercises = [{"name": s.get("exercise_name"), "key": s.get("exercise_key"),
                          "sets": [{"reps": s.get("reps_done"), "weight_kg": s.get("weight_kg"), "rir": s.get("rir")}]}
                         for s in j.get("sets") or [] if isinstance(s, dict)]
            p = {**p, "date": j.get("date") or p.get("date"), "day_key": j.get("day_key") or p.get("day_key"),
                 "notes": j.get("notes") or p.get("notes")}
        else:
            return {"ok": False, "error": "no_exercises", "hint": "exercises:[{name, sets:[{reps, weight_kg}]}]"}
    date = str(p.get("date") or "").strip() or _d._today()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        return {"ok": False, "error": "date YYYY-MM-DD required"}
    try:
        start = time.mktime(time.strptime(date + " 18:00", "%Y-%m-%d %H:%M"))   # the original app logged at 18:00-18:45
    except ValueError:
        return {"ok": False, "error": "bad_date"}
    db = _d._load()
    pr = _d._current_program(db) or {}
    sid = _d._id(db)
    count = 0
    rows = []
    for ex in exercises:
        if not isinstance(ex, dict) or not str(ex.get("name") or ex.get("key") or "").strip():
            continue
        name = str(ex.get("name") or prog.en(prog.exercise_name(ex.get("key"), ex.get("key"))))[:80]
        key = _key_for(name, ex.get("key"))
        for j, s in enumerate(_sets_of(ex)):
            rows.append({"id": _d._id(db), "session_id": sid, "exercise_key": key, "exercise_name": name,
                         "muscle_key": None, "set_index": j, "reps_target": None,
                         "reps_done": int(s["reps"]) if s["reps"] is not None else None, "weight_kg": s["weight_kg"],
                         "rir": s["rir"], "completed_at": start + count})
            count += 1
    if not rows:
        return {"ok": False, "error": "no_sets", "hint": "each exercise needs sets with reps or weight"}
    day_key = str(p.get("day_key") or "").strip().lower() or "fullbody"
    db["sessions"].append({"id": sid, "program_key": pr.get("key") or "manual", "version": (db.get("program") or {}).get("version"),
                           "day_key": day_key, "day_index": None, "started_at": start, "ended_at": start + 45 * 60,
                           "status": "done", "notes": str(p.get("notes") or "")[:200], "source": "manual"})
    db["sets"].extend(rows)
    _refresh_plan_silently(db)
    _d._save(db)
    return {"ok": True, "session": sid, "date": date, "day_key": day_key, "sets": len(rows)}


def _apply_ops(db: dict, s: dict, ops: list) -> tuple[int, int]:
    """the original app's session editor: ops validated against E1/E1.1 numbering first; none valid → nothing touched."""
    sid = s["id"]
    mine = sorted([x for x in db["sets"] if x.get("session_id") == sid],
                  key=lambda x: (x.get("completed_at") or 0, x.get("set_index") or 0, x.get("id") or 0))
    groups, seen = [], {}
    for x in mine:
        k = x.get("exercise_key") or x.get("exercise_name") or "?"
        if k not in seen:
            seen[k] = len(groups)
            groups.append({"k": k, "key": x.get("exercise_key"), "name": x.get("exercise_name") or k, "rows": []})
        groups[seen[k]]["rows"].append(x)
    valid = []
    for op in ops:
        if not isinstance(op, dict) or not op.get("op"):
            continue
        idx = _num(op.get("exercise_index"))
        g = groups[int(idx) - 1] if idx is not None and 1 <= idx <= len(groups) else None
        kind = op["op"]
        if kind == "replace_exercise" and g and _sets_of(op):
            valid.append(("replace", g, str(op.get("name") or g["name"])[:80], _sets_of(op)))
        elif kind == "delete_exercise" and g:
            valid.append(("delete_ex", g))
        elif kind in ("edit_set", "delete_set") and g:
            si = _num(op.get("set_index"))
            row = g["rows"][int(si)] if si is not None and 0 <= si < len(g["rows"]) else None
            if row and kind == "edit_set":
                valid.append(("edit", row, _num(op.get("reps"), 0, 1000) if op.get("reps") is not None else row.get("reps_done"),
                              _num(op.get("weight_kg"), 0, 1000) if op.get("weight_kg") is not None else row.get("weight_kg")))
            elif row:
                valid.append(("delete_set", row))
        elif kind == "add_set" and g:
            last = g["rows"][-1] if g["rows"] else {}
            valid.append(("add_set", g, _num(op.get("reps"), 0, 1000) if op.get("reps") is not None else last.get("reps_done"),
                          _num(op.get("weight_kg"), 0, 1000) if op.get("weight_kg") is not None else last.get("weight_kg")))
        elif kind == "add_exercise" and op.get("name") and _sets_of(op):
            valid.append(("add_ex", str(op["name"])[:80], _sets_of(op)))
    if not valid:
        return 0, 0
    t_end = max([x.get("completed_at") or 0 for x in mine] or [s.get("started_at") or _d._now()])

    def row(key, name, j, reps, w, at):
        return {"id": _d._id(db), "session_id": sid, "exercise_key": key, "exercise_name": name, "muscle_key": None,
                "set_index": j, "reps_target": None, "reps_done": int(reps) if reps is not None else None,
                "weight_kg": w, "rir": None, "completed_at": at}

    for v in valid:
        if v[0] in ("replace", "delete_ex"):           # by the exercise, as the original app's DELETE … WHERE key: a set added
            k = v[1]["k"]                               # earlier in the same edit goes too
            at = min([x.get("completed_at") or 0 for x in v[1]["rows"]] or [t_end])
            db["sets"] = [x for x in db["sets"] if not (x.get("session_id") == sid
                                                        and (x.get("exercise_key") or x.get("exercise_name") or "?") == k)]
            if v[0] == "replace":
                key = _key_for(v[2])
                db["sets"].extend(row(key, v[2], j, st["reps"], st["weight_kg"], at + j * 0.001) for j, st in enumerate(v[3]))
        elif v[0] == "edit":
            v[1]["reps_done"], v[1]["weight_kg"] = (int(v[2]) if v[2] is not None else None), v[3]
        elif v[0] == "delete_set":
            db["sets"] = [x for x in db["sets"] if x is not v[1]]
        elif v[0] == "add_set":
            g = v[1]
            at = max([x.get("completed_at") or 0 for x in g["rows"]] or [t_end]) + 0.001
            db["sets"].append(row(g["key"], g["name"], len(g["rows"]), v[2], v[3], at))
        elif v[0] == "add_ex":
            t_end += 1
            key = _key_for(v[1])
            db["sets"].extend(row(key, v[1], j, st["reps"], st["weight_kg"], t_end + j * 0.001) for j, st in enumerate(v[2]))
    return len(valid), len(valid)


def _a_edit_session(action: str, p: dict) -> dict:
    db = _d._load()
    s = _session(db, p.get("sessionId") or p.get("session"))
    if not s:
        return {"ok": False, "error": "session_not_found"}
    ops = p.get("ops")
    summary = str(p.get("summary") or "")[:200]
    if not isinstance(ops, list) or not ops:
        if not str(p.get("instruction") or "").strip():
            return {"ok": False, "error": "no_ops", "hint": "ops:[{op, exercise_index, set_index, reps, weight_kg}]"}
        r = coach.ask("edit_session", {"instruction": str(p["instruction"])[:1000]})
        if not r.get("ok"):
            return {**r, "hint": "say the change as ops: edit_session {sessionId, ops:[{op:'edit_set', exercise_index:1, set_index:0, reps:12}]}"}
        j = r.get("json") or {}
        if j.get("error"):
            return {"ok": False, "error": str(j["error"])[:200]}
        ops, summary = j.get("operations") or [], str(j.get("summary") or "")[:200]
    applied, total = _apply_ops(db, s, ops)
    if not applied:
        return {"ok": False, "error": "no_valid_ops",
                "hint": "name the exercise by its E number (E1 = the first) and the set by its 0-based index"}
    _refresh_plan_silently(db)
    _d._save(db)
    return {"ok": True, "applied": applied, "summary": summary}


def _a_adjust_today(action: str, p: dict) -> dict:
    """Today's workout changed from an instruction («30 minutes only») — a model task: through the seam or not at all."""
    if not str(p.get("instruction") or "").strip():
        return {"ok": False, "error": "no_instruction"}
    r = coach.ask("adjust_today", {"instruction": str(p["instruction"])[:1000]})
    if not r.get("ok"):
        return {**r, "hint": "start_session with another `day`, or `skip_exercise` during the session"}
    return {"ok": False, "error": "not_wired"}                      # V2-902: apply r["json"]["blocks"] / next_days


def _a_refresh_plan(action: str, p: dict) -> dict:
    db = _d._load()
    r = coach.ask("plan", {})
    if not r.get("ok"):
        return {**r, "hint": "without the trainer, today's day follows the program's rotation"}
    _refresh_plan_silently(db)
    _d._save(db)
    return {"ok": True, "days": len(db.get("plan") or [])}
