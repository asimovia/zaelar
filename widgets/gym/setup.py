"""The gym's setup actions: choosing the program (a new plan VERSION), my gym, and the screen shown (V2-900). Split
from `actions.py` for size only; `data.ACTIONS` maps the names here too.
"""
from __future__ import annotations

import copy

from . import actions as _a
from . import data as _d
from . import program as prog

_num = _a._num


# ── program, configuration, navigation ────────────────────────────────────────────────────────────────────────────

def _a_select_program(action: str, p: dict) -> dict:
    key = str(p.get("program") or "").strip()
    progs = prog.programs()
    if key not in progs:
        if len(progs) == 1 and not key:
            key = next(iter(progs))
        else:
            return {"ok": False, "error": "unknown_program", "programs": sorted(progs)}
    db = _d._load()
    cur = db.get("program")
    if cur and cur.get("key") == key:              # the same program keeps its progress (the original app's «preserved»)
        return {"ok": True, "preserved": True, "version": cur.get("version")}
    version = 1 + max([v.get("version") or 0 for v in db["versions"] if v.get("program_key") == key] or [0])
    db["versions"].append({"program_key": key, "version": version, "at": _d._now(),
                           "reason": str(p.get("reason") or "select")[:120], "snapshot": copy.deepcopy(progs[key])})
    db["program"] = {"key": key, "version": version, "started_at": _d._now(), "day_index": 0}
    db["view"] = {"name": "home", "n": int((db.get("view") or {}).get("n") or 0) + 1}
    _d._save(db)
    return {"ok": True, "program": key, "version": version}


def _a_configure(action: str, p: dict) -> dict:
    db = _d._load()
    changed = []
    eq = p.get("equipment")
    if isinstance(eq, dict):
        for k in _d.EQUIPMENT:
            if k in eq:
                db["equipment"][k] = bool(eq[k])
        changed.append("equipment")
    elif isinstance(eq, list):
        db["equipment"] = {k: k in eq for k in _d.EQUIPMENT}
        changed.append("equipment")
    if "preferences" in p:
        db["preferences"] = str(p.get("preferences") or "")[:4000]
        changed.append("preferences")
    if "age" in p:
        db["age"] = _num(p.get("age"), 10, 100)
        changed.append("age")
    if not changed:
        return {"ok": False, "error": "nothing_to_change", "fields": ["equipment", "preferences", "age"]}
    _d._save(db)
    return {"ok": True, "changed": changed}


def _a_open_view(action: str, p: dict) -> dict:
    name = str(p.get("view") or "home").strip().lower()
    if name not in _d.VIEWS:
        return {"ok": False, "error": "unknown_view", "views": list(_d.VIEWS)}
    db = _d._load()
    arg = p.get("sessionId") or p.get("session") or p.get("exercise") or p.get("date")
    db["view"] = {"name": name, "n": int((db.get("view") or {}).get("n") or 0) + 1, "arg": str(arg)[:60] if arg else None}
    _d._save(db)
    return {"ok": True, "view": name}
