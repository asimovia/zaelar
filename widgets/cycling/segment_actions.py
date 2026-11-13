"""What each cycling action on SEGMENTS and on the open services does, one function per action (V2-901); the rest
are in `actions.py`, and `data.ACTIONS` maps the manifest's names to both.

Every module-level name of `data` is read through the alias (`_d.<name>`), so a patch on `data` governs every call.
"""
from __future__ import annotations

import time

from . import data as _d
from . import engine as E
from . import ghost as G
from . import net
from . import readiness as RD
from . import segments as SG
from . import tracks as T
from .actions import _NAME_MAX, _ui

_DETAIL_BUDGET_S = 6.5        # a network action stops starting calls past this (the widget pool allows 8 s)


# ── Segments ─────────────────────────────────────────────────────────────────────────────────────────────────────

def _geometry(db: dict, p: dict) -> tuple[dict | None, str]:
    s = _d.resolve_ride(db, p.get("ride"))
    if not s:
        return None, "ride_not_found"
    tps = T.load(s["id"])
    if not tps:
        return None, "this ride has no trackpoints"
    start, end = p.get("start"), p.get("end")
    if (not start or not end) and p.get("from_km") is not None and p.get("to_km") is not None:
        try:
            start, end = SG.point_at_km(tps, float(p["from_km"])), SG.point_at_km(tps, float(p["to_km"]))
        except (TypeError, ValueError):
            return None, "from_km and to_km are numbers"
    ok = all(isinstance(x, (list, tuple)) and len(x) >= 2 and all(isinstance(v, (int, float)) for v in x[:2])
             for x in (start, end))
    if not ok:
        return None, "mark a start and an end on the ride (start/end as [lat, lng], or from_km/to_km)"
    geo = SG.segment_from_ride(tps, start, end)
    if not geo or (geo["distance_m"] or 0) < 50:
        return None, "the start and the end are the same place: mark a longer stretch"
    return geo, ""


def a_create_segment(action: str, p: dict) -> dict:
    db = _d._load()
    name = str(p.get("name") or "").strip()[:_NAME_MAX]
    if not name:
        return {"ok": False, "error": "a segment needs a name"}
    geo, err = _geometry(db, p)
    if not geo:
        return {"ok": False, "error": err}
    seg = {"id": SG._next_id(db, "segment"), "name": name, "distance_m": geo["distance_m"],
           "start_lat": geo["start_lat"], "start_lng": geo["start_lng"], "end_lat": geo["end_lat"],
           "end_lng": geo["end_lng"], "polyline": geo["polyline"], "ele_gain_m": geo["ele_gain_m"],
           "pr_time_sec": None, "pr_session_id": None, "pr_at": None, "attempts": 0,
           "source": "manual_post", "created_at": E.now_iso()}
    db.setdefault("segments", []).append(seg)
    res = SG.backfill_segment_attempts(db, seg["id"], T.load)    # every earlier ride, ranked
    _ui(db, "segment", segment=seg["id"])
    _d._save(db)
    return {"ok": True, "segment": seg["id"], "name": name, "distance_m": seg["distance_m"],
            "passes": len(res["ranking"]), "ranking": res["ranking"][:20]}


def a_redo_segment(action: str, p: dict) -> dict:
    db = _d._load()
    seg = _d.resolve_segment(db, p.get("segment"))
    if not seg:
        return {"ok": False, "error": "segment_not_found"}
    geo, err = _geometry(db, p)
    if not geo:
        return {"ok": False, "error": err}
    if str(p.get("name") or "").strip():
        seg["name"] = str(p["name"]).strip()[:_NAME_MAX]
    seg.update({k: geo[k] for k in ("start_lat", "start_lng", "end_lat", "end_lng", "distance_m", "polyline", "ele_gain_m")})
    res = SG.backfill_segment_attempts(db, seg["id"], T.load)
    _d._save(db)
    return {"ok": True, "segment": seg["id"], "distance_m": seg["distance_m"], "passes": len(res["ranking"]),
            "ranking": res["ranking"][:20]}


def a_rename_segment(action: str, p: dict) -> dict:
    db = _d._load()
    seg = _d.resolve_segment(db, p.get("segment"))
    if not seg:
        return {"ok": False, "error": "segment_not_found"}
    seg["name"] = str(p.get("name") or "").strip()[:_NAME_MAX] or seg.get("name") or "Segment"
    _d._save(db)
    return {"ok": True, "segment": seg["id"], "name": seg["name"]}


def a_delete_segment(action: str, p: dict) -> dict:
    db = _d._load()
    seg = _d.resolve_segment(db, p.get("segment"))
    if not seg:
        return {"ok": False, "error": "segment_not_found"}
    db["segments"] = [s for s in db.get("segments") or [] if s.get("id") != seg["id"]]
    db["attempts"] = [a for a in db.get("attempts") or [] if a.get("segment_id") != seg["id"]]
    cur = db.get("current")
    if cur:
        g = cur.get("ghost") or {}
        g["inside"] = [s for s in g.get("inside") or [] if s["id"] != seg["id"]]
        if g.get("selected") == seg["id"]:
            g["selected"] = g["inside"][0]["id"] if g["inside"] else None
    if (db.get("ui") or {}).get("segment") == seg["id"]:
        _ui(db, "segments")
    _d._save(db)
    return {"ok": True, "deleted": seg["id"]}


def a_recalc_segment(action: str, p: dict) -> dict:
    db = _d._load()
    seg = _d.resolve_segment(db, p.get("segment"))
    if not seg:
        return {"ok": False, "error": "segment_not_found"}
    res = SG.backfill_segment_attempts(db, seg["id"], T.load)
    _d._save(db)
    return {"ok": True, "segment": seg["id"], "passes": len(res["ranking"]), "pr_time_sec": res["segment"]["pr_time_sec"]}


def a_ghost_select(action: str, p: dict) -> dict:
    db = _d._load()
    cur = db.get("current")
    if not cur:
        return {"ok": False, "error": "no ride is being recorded"}
    seg = _d.resolve_segment(db, p.get("segment"))
    if not seg or not G.select(cur, seg["id"]):
        return {"ok": False, "error": "not inside that segment now",
                "inside": [s["name"] for s in (cur.get("ghost") or {}).get("inside") or []]}
    _d._save(db)
    return {"ok": True, "selected": seg["id"]}


# ── Readiness, gaps, the ride's town and temperature (the network actions) ───────────────────────────────────────

def a_readiness(action: str, p: dict) -> dict:
    db = _d._load()
    if not p.get("force") and RD.fresh(db.get("readiness")):
        return {"ok": True, "cached": True, **db["readiness"]}
    lat, lng = p.get("lat"), p.get("lng", p.get("lon"))
    r = RD.compute(db, lat, lng)
    db["readiness"] = r
    _d._save(db)
    return {"ok": True, **r}


def a_reconstruct_gaps(action: str, p: dict) -> dict:
    """Rebuild every GPS gap over 30 s of a saved ride along real roads; as many as fit this call, the rest on the
    next one (it says how many are left)."""
    db = _d._load()
    s = _d.resolve_ride(db, p.get("ride"))
    if not s:
        return {"ok": False, "error": "ride_not_found"}
    t0 = time.time()
    gaps = E.find_gaps(T.load(s["id"]))
    filled, inserted, added_m, failures, virt_all = 0, 0, 0.0, 0, []
    for g in gaps:
        if time.time() - t0 > _DETAIL_BUDGET_S - net.TIMEOUT_S:
            break
        rt = net.route(g["prev"], g["curr"])
        if not rt or not rt.get("coordinates"):
            failures += 1
            continue
        virt = E.interpolate_trackpoints(g["prev"], g["curr"], rt["coordinates"])
        virt_all += virt
        filled += 1
        inserted += len(virt)
        added_m += rt.get("distance_m") or 0
    T.merge(s["id"], virt_all)
    _d._save(db)
    return {"ok": True, "gaps_found": len(gaps), "gaps_filled": filled, "trackpoints_inserted": inserted,
            "distance_added_m": E.jround(added_m), "failures": failures,
            "left": max(0, len(gaps) - filled - failures)}


def a_enrich(action: str, p: dict) -> dict:
    """The town a ride started in and the temperature it was ridden in (best-effort, one ride per call)."""
    db = _d._load()
    s = _d.resolve_ride(db, p.get("ride"))
    if not s or s.get("start_lat") is None:
        return {"ok": False, "error": "ride_not_found" if not s else "no position"}
    changed = False
    if not s.get("locality"):
        place = net.locality(s["start_lat"], s["start_lng"], str(p.get("lang") or "en")[:5])
        if place:
            s["locality"], changed = place, True
        else:
            s["locality_tried"] = True
    if s.get("weather_temp_c") is None and s.get("status") == "done":
        t = net.temp_at(s["start_lat"], s["start_lng"], s.get("started_at"))
        if t is not None:
            s["weather_temp_c"], changed = t, True
        else:
            s["temp_tried"] = True
    _d._save(db)
    return {"ok": True, "ride": s["id"], "locality": s.get("locality"), "weather_temp_c": s.get("weather_temp_c"),
            "changed": changed}
