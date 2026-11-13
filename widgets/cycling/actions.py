"""What each cycling action does, one function per action; `data.ACTIONS` maps the manifest's names to them.

Every module-level name of `data` is read through the alias (`_d.<name>`), so a patch on `data` governs every call.
"""
from __future__ import annotations

import time

from . import data as _d
from . import engine as E
from . import segments as SG
from . import ghost as G
from . import recorder as R
from . import tracks as T

_NAME_MAX = 60


def _now() -> float:
    return time.time() * 1000


def _ui(db: dict, view: str, ride=None, segment=None) -> None:
    ui = db.setdefault("ui", {"n": 0})
    ui.update(view=view, ride=ride, segment=segment, n=int(ui.get("n") or 0) + 1)


def _int_or_none(x):
    try:
        v = int(float(x))
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


# ── The ride: start, pause, resume, save, discard, and the screen that records it ───────────────────────────────

def a_start(action: str, p: dict) -> dict:
    db = _d._load()
    cur = db.get("current")
    if db.get("status") == "running" and cur:
        return {"ok": True, "already": True, "status": "running", "ride": cur["id"]}
    z = _d.zones(db)
    zmin, zmax = _int_or_none(p.get("hr_zone_min")) or z["min"], _int_or_none(p.get("hr_zone_max")) or z["max"]
    preset = str(p.get("zone") or "").lower()
    if preset in z["defaults"] and isinstance(z["defaults"][preset], dict):
        zmin, zmax = z["defaults"][preset]["min"] or None, z["defaults"][preset]["max"]
    now = _now()
    rid = SG._next_id(db, "session")
    cur = R.new_ride(rid, now, zmin, zmax)
    db["current"], db["status"] = cur, "running"
    db.setdefault("sessions", []).append({
        "id": rid, "started_at": cur["started_at"], "ended_at": None, "status": "active", "duration_sec": None,
        "distance_km": None, "avg_speed_kmh": None, "max_speed_kmh": None, "avg_hr": None, "max_hr": None,
        "elevation_gain_m": None, "hr_zone_min": zmin, "hr_zone_max": zmax, "notes": None,
        "name": (str(p.get("name") or "").strip()[:_NAME_MAX] or None), "weather_temp_c": None, "locality": None,
        "start_lat": None, "start_lng": None})
    _ui(db, "recording", ride=rid)
    _d._save(db)
    return {"ok": True, "status": "running", "ride": rid, "countdown_s": R.COUNTDOWN_S, "zone": [zmin, zmax]}


def a_pause(action: str, p: dict) -> dict:
    db = _d._load()
    cur = db.get("current")
    if not cur:
        return {"ok": False, "error": "no ride is being recorded"}
    if R.is_paused(cur):
        return {"ok": True, "paused": True, "already": True}
    cur.setdefault("pauses", []).append([_now(), None])
    _d._save(db)
    return {"ok": True, "paused": True}


def a_resume(action: str, p: dict) -> dict:
    db = _d._load()
    cur = db.get("current")
    if not cur:
        return {"ok": False, "error": "no ride is being recorded"}
    if not R.is_paused(cur):
        return {"ok": True, "paused": False, "already": True}
    cur["pauses"][-1][1] = _now()
    _d._save(db)
    return {"ok": True, "paused": False}


def a_stop(action: str, p: dict) -> dict:
    """SAVE the ride: close it with its summary, then run it against every segment (the source's post-production)."""
    db = _d._load()
    cur = db.get("current")
    if not cur:
        return {"ok": True, "status": "idle", "note": "no ride was being recorded"}
    now = max(_now(), float((cur.get("last_acc") or [0])[0]))   # a batch can carry fixes stamped after this call
    if R.is_paused(cur):
        cur["pauses"][-1][1] = now
    sm = R.summary(cur, now)
    sess = SG.get_session(db, cur["id"])
    tps = T.load(cur["id"])
    st = E.compute_session_stats(tps) or {}
    sess.update(ended_at=E.iso(now), status="done", duration_sec=sm["duration_sec"],
                distance_km=E.jround(sm["distance_km"], 3), avg_speed_kmh=sm["avg_speed_kmh"],
                max_speed_kmh=sm["max_speed_kmh"], avg_hr=st.get("avg_hr"), max_hr=st.get("max_hr"),
                elevation_gain_m=st.get("elevation_gain_m"), start_lat=cur.get("start_lat"),
                start_lng=cur.get("start_lng"))
    res = SG.process_session_segments(db, cur["id"], T.load)
    db["current"], db["status"] = None, "idle"
    _ui(db, "history")
    _d._save(db)
    prs = sum(1 for x in res["passes"] if x.get("isPr"))
    return {"ok": True, "status": "idle", "ride": cur["id"], "summary": _d.ride_summary(sess),
            "segments_passed": len(res["passes"]), "prs": prs,
            "passes": [{"segment": x["segment_name"], "time_sec": x["time_sec"], "pr": x["isPr"]} for x in res["passes"]]}


def a_discard(action: str, p: dict) -> dict:
    """Throw the ride away: its record, its trackpoints, nothing kept."""
    db = _d._load()
    cur = db.get("current")
    if not cur:
        return {"ok": True, "status": "idle", "note": "no ride was being recorded"}
    _drop_ride(db, cur["id"])
    db["current"], db["status"] = None, "idle"
    _ui(db, "menu")
    _d._save(db)
    return {"ok": True, "status": "idle", "discarded": cur["id"]}


def a_claim(action: str, p: dict) -> dict:
    db = _d._load()
    cur, owner = db.get("current"), str(p.get("owner") or "")[:64]
    if not cur or not owner:
        return {"ok": False, "error": "no ride to claim" if not cur else "owner is required"}
    if cur.get("owner") and cur["owner"] != owner:
        return {"ok": False, "owned_by_another_screen": True}
    if not cur.get("owner"):
        cur["owner"] = owner
        _d._save(db)
    return {"ok": True, "owner": owner, "countdown_until_ms": cur["countdown_until_ms"]}


def a_samples(action: str, p: dict) -> dict:
    db = _d._load()
    cur = db.get("current")
    if not cur:
        return {"ok": False, "error": "no ride is being recorded"}
    if cur.get("owner") != str(p.get("owner") or ""):
        return {"ok": False, "owned_by_another_screen": True}
    batch = [s for s in (p.get("samples") or [])[:5000] if isinstance(s, dict)]
    taken, tps = R.take(cur, batch, db.get("segments") or [], _d.pr_paths(db, cur))
    T.append(cur["id"], tps)
    sess = SG.get_session(db, cur["id"])
    if sess and sess.get("start_lat") is None and cur.get("start_lat") is not None:
        sess["start_lat"], sess["start_lng"] = cur["start_lat"], cur["start_lng"]
    _d._save(db)
    return {"ok": True, "taken": taken, "kept": len(tps)}


# ── Zones, screens ───────────────────────────────────────────────────────────────────────────────────────────────

def a_set_zone(action: str, p: dict) -> dict:
    db = _d._load()
    z = db.setdefault("zone", {"min": None, "max": None, "age": None})
    if p.get("age") is not None:
        age = _int_or_none(p.get("age"))
        if not age or not 8 <= age <= 100:
            return {"ok": False, "error": "age must be between 8 and 100"}
        z["age"] = age
    d = E.default_hr_zones(z.get("age"))
    preset = str(p.get("zone") or "").lower()
    if preset:
        if preset not in d or not isinstance(d[preset], dict):
            return {"ok": False, "error": f"unknown zone '{preset}'", "zones": ["z1", "z2", "z3", "z4", "z5"]}
        z["min"], z["max"] = d[preset]["min"] or None, d[preset]["max"]
    if p.get("min") is not None or p.get("max") is not None:
        lo, hi = _int_or_none(p.get("min")) or z.get("min"), _int_or_none(p.get("max")) or z.get("max")
        if not lo or not hi or not 40 <= lo < hi <= 230:
            return {"ok": False, "error": "a zone is two heart rates, low < high, between 40 and 230"}
        z["min"], z["max"] = lo, hi
    cur = db.get("current")
    if cur and (preset or p.get("min") is not None or p.get("max") is not None):
        cur["hr_zone_min"], cur["hr_zone_max"] = z["min"], z["max"]
    _d._save(db)
    zz = _d.zones(db)
    return {"ok": True, "zone": [zz["min"], zz["max"]], "age": zz["age"], "hr_max": zz["defaults"]["hr_max"]}


def a_show(action: str, p: dict) -> dict:
    db = _d._load()
    view = str(p.get("view") or "").lower() or ("ride" if p.get("ride") else "segment" if p.get("segment") else "menu")
    if view not in _d.VIEWS:
        return {"ok": False, "error": f"unknown view '{view}'", "views": list(_d.VIEWS)}
    ride = seg = None
    if view == "ride":
        s = _d.resolve_ride(db, p.get("ride") or "last")
        if not s:
            return {"ok": False, "error": "ride_not_found"}
        ride = s["id"]
    if view == "segment":
        s = _d.resolve_segment(db, p.get("segment"))
        if not s:
            return {"ok": False, "error": "segment_not_found"}
        seg = s["id"]
    if view == "recording" and db.get("status") != "running":
        view = "menu"
    _ui(db, view, ride=ride, segment=seg)
    _d._save(db)
    return {"ok": True, "view": view, "ride": ride, "segment": seg}


def a_ride_detail(action: str, p: dict) -> dict:
    db = _d._load()
    s = _d.resolve_ride(db, p.get("ride"))
    if not s:
        return {"ok": False, "error": "ride_not_found"}
    return {"ok": True, **_d.ride_detail(db, s)}


def a_segment_detail(action: str, p: dict) -> dict:
    db = _d._load()
    s = _d.resolve_segment(db, p.get("segment"))
    if not s:
        return {"ok": False, "error": "segment_not_found"}
    return {"ok": True, **_d.segment_detail(db, s)}


# ── Rides: rename, delete ────────────────────────────────────────────────────────────────────────────────────────

def a_rename_ride(action: str, p: dict) -> dict:
    db = _d._load()
    s = _d.resolve_ride(db, p.get("ride"))
    if not s:
        return {"ok": False, "error": "ride_not_found"}
    s["name"] = str(p.get("name") or "").strip()[:_NAME_MAX] or None
    _d._save(db)
    return {"ok": True, "ride": s["id"], "name": s["name"]}


def _drop_ride(db: dict, rid) -> None:
    hit = {a["segment_id"] for a in db.get("attempts") or [] if a.get("session_id") == rid}
    db["attempts"] = [a for a in db.get("attempts") or [] if a.get("session_id") != rid]
    db["sessions"] = [s for s in db.get("sessions") or [] if s.get("id") != rid]
    for sid in hit:
        SG.refresh_segment_pr(db, sid)      # a deleted ride's time no longer stands as a PR
    T.delete(rid)


def a_delete_ride(action: str, p: dict) -> dict:
    db = _d._load()
    s = _d.resolve_ride(db, p.get("ride"))
    if not s:
        return {"ok": False, "error": "ride_not_found"}
    if (db.get("current") or {}).get("id") == s["id"]:
        return {"ok": False, "error": "this ride is being recorded: discard it instead"}
    _drop_ride(db, s["id"])
    ui = db.get("ui") or {}
    if ui.get("ride") == s["id"]:
        _ui(db, "history")
    _d._save(db)
    return {"ok": True, "deleted": s["id"]}
