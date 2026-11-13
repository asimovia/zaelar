"""Cycling — rides with GPS and heart rate, the ghost rider, segments and their PRs (V2-901).

Ported from the person's previous app (rides, segments, the matcher, stats and splits, the live ghost) to work the
same inside the agent. One person, one store: `state.json` keeps the rides' summaries, the segments and their
attempts; each ride's trackpoints live in their own file under the app's data directory (`tracks.py`). The screen
that owns a ride reads the phone's sensors through `ctx.device().activity()` and sends batches here (`samples`);
`recorder.py` turns them into figures and trackpoints exactly as the source did on each GPS fix, `ghost.py` races
him against his earlier attempts, `engine.py` holds the maths, `net.py` the three open services (temperature,
town, road routing), `readiness.py` the «ready to ride?» lights. The handlers are one function each in
`actions.py`; `ACTIONS` below is the table the manifest's names map to.

Rules: nothing starts by itself (`start` comes from his tap or his request); one ride at a time; a batch from a
screen that does not own the ride is refused; a reading we do not have is `None`, never a zero.
"""
from __future__ import annotations

import logging
import math
import time

from .. import store
from . import engine as E
from . import segments as SG
from . import ghost as G
from . import recorder as R
from . import tracks as T

WID = "cycling"
DB_VERSION = 1
log = logging.getLogger("widgets.cycling")

RIDES_IN_VIEW = 100
LIVE_ROUTE_POINTS = 400
DETAIL_ROUTE_POINTS = 800
PROFILE_POINTS = 240
PR_POLYLINE_POINTS = 120
VIEWS = ("menu", "history", "ride", "segments", "segment", "recording")


def _default() -> dict:
    return {"_v": DB_VERSION, "status": "idle", "current": None, "zone": {"min": None, "max": None, "age": None},
            "sessions": [], "segments": [], "attempts": [], "next_id": {},
            "ui": {"view": "menu", "ride": None, "segment": None, "n": 0}, "readiness": None}


def _migrate(db: dict, _from_v) -> dict:
    base = _default()
    for k, v in base.items():
        db.setdefault(k, v)
    return db


def _load() -> dict:
    return store.load(WID, _default(), version=DB_VERSION, migrate=_migrate)


def _save(db: dict) -> None:
    store.save(WID, db)


def _thin(pts: list, n: int) -> list:
    if len(pts) <= n:
        return list(pts)
    step = math.ceil(len(pts) / n)
    out = pts[::step]
    if out[-1] is not pts[-1]:
        out.append(pts[-1])
    return out


def zones(db: dict) -> dict:
    z = db.get("zone") or {}
    d = E.default_hr_zones(z.get("age"))
    return {"min": z.get("min") or d["z2"]["min"], "max": z.get("max") or d["z2"]["max"], "age": z.get("age"),
            "defaults": d}


# ── Rides, segments: what the lists show and how a spoken reference finds one ────────────────────────────────────

def ride_summary(s: dict) -> dict:
    keys = ("id", "name", "started_at", "ended_at", "status", "duration_sec", "distance_km", "avg_speed_kmh",
            "max_speed_kmh", "avg_hr", "max_hr", "elevation_gain_m", "weather_temp_c", "locality", "start_lat",
            "start_lng", "locality_tried", "temp_tried")
    return {k: s.get(k) for k in keys}


def _ride_label(s: dict) -> str:
    day = str(s.get("started_at") or "")[:10]
    bits = [s.get("name") or "", s.get("locality") or "", day, f"{(s.get('distance_km') or 0):.1f} km"]
    return " · ".join(b for b in bits if b)


def resolve_ride(db: dict, ref) -> dict | None:
    """A ride from an id, «last», or words of its name / town / date."""
    rides = sorted(db.get("sessions") or [], key=lambda s: str(s.get("started_at")), reverse=True)
    if ref is None or ref == "":
        return None
    if isinstance(ref, (int, float)) and not isinstance(ref, bool):
        return SG.get_session(db, int(ref))
    r = str(ref).strip().lower()
    if r.isdigit():
        return SG.get_session(db, int(r))
    if r in ("last", "latest", "última", "ultima", "la última", "la ultima", "the last one", "last ride"):
        done = [s for s in rides if s.get("status") == "done"]
        return done[0] if done else (rides[0] if rides else None)
    for s in rides:
        if r and r in _ride_label(s).lower():
            return s
    return None


def resolve_segment(db: dict, ref) -> dict | None:
    if ref is None or ref == "":
        return None
    if isinstance(ref, (int, float)) and not isinstance(ref, bool):
        return SG.get_segment(db, int(ref))
    r = str(ref).strip().lower()
    if r.isdigit():
        return SG.get_segment(db, int(r))
    for s in db.get("segments") or []:
        if r and r in str(s.get("name") or "").lower():
            return s
    return None


def ref_index() -> list[dict]:
    """The rides and segments a spoken reference can name («yesterday's ride», «the climb»)."""
    try:
        db = _load()
        out = [{"id": str(s["id"]), "label": _ride_label(s), "field": "ride", "hint": "ride"}
               for s in sorted(db.get("sessions") or [], key=lambda s: str(s.get("started_at")), reverse=True)[:40]]
        out += [{"id": str(s["id"]), "label": str(s.get("name") or ""), "field": "segment", "hint": "segment"}
                for s in db.get("segments") or []]
        return out
    except Exception as e:  # noqa: BLE001 — no index is no resolution, never a broken turn
        log.warning(f"cycling: ref_index failed: {e}")
        return []


# ── The ghost's data for a segment (rivals + the PR's real path), cached per state of its attempts ──────────────

_GHOST_CACHE: dict = {}


def segment_ghost(db: dict, seg_id) -> dict | None:
    seg = SG.get_segment(db, seg_id)
    if not seg:
        return None
    atts = sorted((a for a in db.get("attempts") or [] if a.get("segment_id") == seg_id and (a.get("time_sec") or 0) > 0),
                  key=lambda a: a["time_sec"])[:50]
    key = (seg_id, len(atts), seg.get("pr_session_id"), seg.get("pr_time_sec"))
    hit = _GHOST_CACHE.get(seg_id)
    if hit and hit[0] == key:
        return hit[1]
    rows = []
    for a in atts:
        s = SG.get_session(db, a["session_id"]) or {}
        rows.append({"id": a["id"], "session_id": a["session_id"], "time_sec": a["time_sec"], "is_pr": a.get("is_pr"),
                     "avg_hr": a.get("avg_hr"), "avg_speed_kmh": a.get("avg_speed_kmh"),
                     "session_name": s.get("name"), "session_started_at": s.get("started_at")})
    pr = next((a for a in atts if a.get("is_pr")), atts[0] if atts else None)
    pr_poly = None
    if pr:
        lo, hi = E.ts_ms(pr["started_at"]), E.ts_ms(pr["ended_at"])
        pts = [[p["lat"], p["lng"]] for p in T.load(pr["session_id"]) if lo <= E.ts_ms(p.get("ts")) <= hi]
        if len(pts) > 1:
            pr_poly = _thin(pts, PR_POLYLINE_POINTS)
    out = {"segment_id": seg_id, "attempts": rows, "pr_polyline": pr_poly}
    _GHOST_CACHE[seg_id] = (key, out)
    return out


def pr_paths(db: dict, cur: dict) -> dict:
    sel = (cur.get("ghost") or {}).get("selected")
    g = segment_ghost(db, sel) if sel else None
    return {sel: g["pr_polyline"]} if g and g.get("pr_polyline") else {}


# ── The view every screen gets ───────────────────────────────────────────────────────────────────────────────────

def _live(db: dict, cur: dict, now_ms: float) -> dict:
    zone = zones(db)
    zmin, zmax = cur.get("hr_zone_min") or zone["min"], cur.get("hr_zone_max") or zone["max"]
    el = R.elapsed_s(cur, now_ms)
    hr = R.hr_now(cur, now_ms)
    g = cur.get("ghost") or {}
    segs = {s["id"]: s for s in db.get("segments") or []}
    act = G.active(cur)
    sel = g.get("selected")
    ghost_data = segment_ghost(db, sel) if sel else None
    approach = g.get("approach")
    if approach and not ghost_data:
        ghost_data = segment_ghost(db, approach["id"])     # preloaded so the map has it ready, as the source did
    nearby = []
    for n in g.get("nearby") or []:
        s = segs.get(n["id"])
        if s:
            nearby.append({"id": s["id"], "name": s.get("name"), "dist_m": n["dist_m"],
                           "distance_m": s.get("distance_m"), "pr_time_sec": s.get("pr_time_sec"),
                           "start": [s["start_lat"], s["start_lng"]], "end": [s["end_lat"], s["end_lng"]],
                           "polyline": _thin(G.polyline_for(s) or [], 100)})
    return {
        "id": cur["id"], "owner": cur.get("owner"), "started_ms": cur["started_ms"],
        "countdown_until_ms": cur["countdown_until_ms"], "paused": R.is_paused(cur), "elapsed_s": el,
        "distance_km": E.jround(cur["distance_km"], 3), "speed_kmh": cur.get("speed") or 0,
        "avg_speed_kmh": E.jround(cur["distance_km"] / (el / 3600), 2) if el and cur["distance_km"] else None,
        "max_speed_kmh": cur.get("max_speed") or 0, "altitude_m": cur.get("altitude"),
        "heart_rate": hr, "has_heart_rate": bool(cur.get("hr")),
        "zone": {"min": zmin, "max": zmax}, "zone_status": E.hr_zone_status(hr, zmin, zmax),
        "has_location": cur.get("last_lat") is not None, "route": _thin(cur.get("route") or [], LIVE_ROUTE_POINTS),
        "last": [cur["last_lat"], cur["last_lng"]] if cur.get("last_lat") is not None else None,
        "reconstructed": cur.get("reconstructed") or 0, "events": (cur.get("events") or [])[-5:],
        "ghost": {
            "inside": [{k: s.get(k) for k in ("id", "name", "distance_m", "pr_time_sec", "entered_ms", "dist_accum")}
                       for s in g.get("inside") or []],
            "selected": sel, "approach": approach, "nearby": nearby,
            "active": ({k: act.get(k) for k in ("id", "name", "distance_m", "pr_time_sec", "entered_ms", "dist_accum")}
                       if act else None),
            "segment": ({k: segs[sel].get(k) for k in ("id", "name", "distance_m", "pr_time_sec", "start_lat", "start_lng",
                                                       "end_lat", "end_lng")} if sel in segs else None),
            "attempts": (ghost_data or {}).get("attempts") if ghost_data and ghost_data["segment_id"] == sel else [],
            "pr_polyline": (ghost_data or {}).get("pr_polyline") if ghost_data else None,
            "pr_polyline_of": (ghost_data or {}).get("segment_id") if ghost_data else None,
        },
    }


def view_data(q: str = "") -> dict:
    try:
        db = _load()
        now = time.time() * 1000
        rides = sorted(db.get("sessions") or [], key=lambda s: str(s.get("started_at")), reverse=True)
        out = {
            "status": db.get("status", "idle"),
            "zone": zones(db),
            "rides": [ride_summary(s) for s in rides[:RIDES_IN_VIEW]],
            "rides_total": len(rides),
            "segments": [{k: s.get(k) for k in ("id", "name", "distance_m", "pr_time_sec", "pr_session_id", "attempts",
                                                 "start_lat", "start_lng", "end_lat", "end_lng", "created_at")}
                         for s in sorted(db.get("segments") or [], key=lambda s: -int(s.get("id") or 0))],
            "ui": db.get("ui") or {"view": "menu", "n": 0},
            "readiness": db.get("readiness"),
            "paused": False,
        }
        cur = db.get("current")
        if db.get("status") == "running" and cur:
            out["current"] = _live(db, cur, now)
            out["paused"] = out["current"]["paused"]
        return out
    except Exception as e:  # noqa: BLE001 — a broken store is an empty card that says so, never a dead turn
        return {"status": "idle", "rides": [], "segments": [], "ui": {"view": "menu", "n": 0}, "error": str(e)[:120]}


def ride_detail(db: dict, s: dict) -> dict:
    """Everything the ride's page shows: route, figures, analysis, splits, heart rate and climb profiles, the
    segments it crossed, the gaps in its GPS."""
    tps = T.load(s["id"])
    geo = [p for p in tps if p.get("lat") is not None]
    t0 = E.ts_ms(geo[0]["ts"]) if geo else 0
    hr = [[E.jround((E.ts_ms(p["ts"]) - t0) / 1000), p["heart_rate"]] for p in geo if p.get("heart_rate")]
    elev, acc = [], 0.0
    for i, p in enumerate(geo):
        if i:
            acc += E.haversine_km(geo[i - 1]["lat"], geo[i - 1]["lng"], p["lat"], p["lng"])
        if p.get("altitude_m") is not None:
            elev.append([E.jround(acc, 3), E.jround(p["altitude_m"], 1)])
    gaps = E.find_gaps(tps)
    return {
        "ride": ride_summary(s),
        "route": _thin([[p["lat"], p["lng"], p.get("altitude_m")] for p in geo], DETAIL_ROUTE_POINTS),
        "hr": _thin(hr, PROFILE_POINTS), "elevation": _thin(elev, PROFILE_POINTS),
        "stats": E.compute_session_stats(tps), "splits": E.compute_session_splits(tps, 1),
        "attempts": SG.list_session_attempts(db, s["id"]),
        "gaps": [{"gap_sec": g["gap_sec"], "idx": g["idx"]} for g in gaps],
        "reconstructed_count": sum(1 for p in tps if p.get("source") == "reconstructed"),
        "trackpoint_count": len(tps),
    }


def segment_detail(db: dict, seg: dict) -> dict:
    atts = SG.list_segment_attempts(db, seg["id"])
    top3 = sorted((a for a in atts if a.get("time_sec") is not None), key=lambda a: a["time_sec"])[:3]
    g = segment_ghost(db, seg["id"]) or {}
    pr_speed = (E.jround((seg["distance_m"] / 1000) / (seg["pr_time_sec"] / 3600), 1)
                if seg.get("pr_time_sec") and seg.get("distance_m") else None)
    return {"segment": {k: seg.get(k) for k in ("id", "name", "distance_m", "pr_time_sec", "pr_session_id", "pr_at",
                                                  "attempts", "start_lat", "start_lng", "end_lat", "end_lng", "source",
                                                  "created_at")},
            "polyline": _thin(G.polyline_for(seg, g.get("pr_polyline")) or [], 300),
            "attempts": atts, "top3": top3, "pr_speed_kmh": pr_speed}


def prompt_digest() -> str:
    """With the card open: the ride in progress (or the last one), so «how fast am I going?» needs no round trip."""
    try:
        db = _load()
        cur = db.get("current")
        if db.get("status") == "running" and cur:
            v = _live(db, cur, time.time() * 1000)
            bits = [f"ride running for {v['elapsed_s'] // 60} min" + (" (paused)" if v["paused"] else ""),
                    f"{v['distance_km']:.2f} km", f"{v['speed_kmh']} km/h now"]
            if v["avg_speed_kmh"] is not None:
                bits.append(f"avg {v['avg_speed_kmh']} km/h")
            if v["heart_rate"] is not None:
                bits.append(f"heart rate {v['heart_rate']} bpm (zone {v['zone']['min']}-{v['zone']['max']}: "
                            f"{v['zone_status']})")
            elif v["has_heart_rate"]:
                bits.append("heart rate: strap not sending right now")
            else:
                bits.append("no heart-rate strap")
            a = v["ghost"]["active"]
            if a:
                el = (time.time() * 1000 - a["entered_ms"]) / 1000
                pr = f", PR {a['pr_time_sec']} s" if a.get("pr_time_sec") else ""
                bits.append(f"inside segment «{a['name']}» for {int(el)} s{pr}")
            elif v["ghost"]["approach"]:
                bits.append(f"approaching segment «{v['ghost']['approach']['name']}»")
            return "Cycling on screen: " + ", ".join(bits) + "."
        done = [s for s in sorted(db.get("sessions") or [], key=lambda s: str(s.get("started_at")), reverse=True)
                if s.get("status") == "done"]
        line = f"Cycling on screen: {len(done)} rides, {len(db.get('segments') or [])} segments"
        if done:
            s = done[0]
            line += (f"; last ride {str(s.get('started_at'))[:10]} {(s.get('distance_km') or 0):.1f} km in "
                     f"{(s.get('duration_sec') or 0) // 60} min" + (f" from {s['locality']}" if s.get("locality") else ""))
        return line + "."
    except Exception as e:  # noqa: BLE001 — a broken digest leaves the turn without the figures, never broken
        log.warning(f"cycling: prompt_digest failed: {e}")
        return ""


from .actions import (  # noqa: E402 — the handlers read this module through an alias
    a_start as _a_start, a_pause as _a_pause, a_resume as _a_resume, a_stop as _a_stop, a_discard as _a_discard,
    a_claim as _a_claim, a_samples as _a_samples, a_set_zone as _a_set_zone, a_show as _a_show,
    a_ride_detail as _a_ride_detail, a_segment_detail as _a_segment_detail, a_rename_ride as _a_rename_ride,
    a_delete_ride as _a_delete_ride,
)
from .segment_actions import (  # noqa: E402
    a_create_segment as _a_create_segment, a_redo_segment as _a_redo_segment, a_rename_segment as _a_rename_segment,
    a_delete_segment as _a_delete_segment, a_recalc_segment as _a_recalc_segment, a_ghost_select as _a_ghost_select,
    a_readiness as _a_readiness, a_reconstruct_gaps as _a_reconstruct_gaps, a_enrich as _a_enrich,
)

ACTIONS = {
    "start": _a_start,
    "pause": _a_pause,
    "resume": _a_resume,
    "stop": _a_stop,
    "discard": _a_discard,
    "claim": _a_claim,
    "samples": _a_samples,
    "set_zone": _a_set_zone,
    "show": _a_show,
    "ride_detail": _a_ride_detail,
    "segment_detail": _a_segment_detail,
    "rename_ride": _a_rename_ride,
    "delete_ride": _a_delete_ride,
    "create_segment": _a_create_segment,
    "redo_segment": _a_redo_segment,
    "rename_segment": _a_rename_segment,
    "delete_segment": _a_delete_segment,
    "recalc_segment": _a_recalc_segment,
    "ghost_select": _a_ghost_select,
    "readiness": _a_readiness,
    "reconstruct_gaps": _a_reconstruct_gaps,
    "enrich": _a_enrich,
}


def apply_action(action: str, payload: dict) -> dict:
    handler = ACTIONS.get(action) if isinstance(action, str) else None
    if handler is None:
        return {"ok": False, "error": "unknown_action", "action": action, "actions": sorted(ACTIONS)}
    try:
        return handler(action, payload if isinstance(payload, dict) else {})
    except Exception as e:  # noqa: BLE001 — an action that breaks says so, it never takes the turn down
        log.warning(f"cycling: {action} failed: {e}")
        return {"ok": False, "error": str(e)[:160]}
