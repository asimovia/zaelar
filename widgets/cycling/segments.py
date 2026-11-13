"""Cycling — the store side of the ride maths: rides, segments, attempts and PRs (V2-901).

Ported 1:1 from the source app's session/segment/attempt queries (its D1 tables become the app's own store: `db`
holds `sessions`, `segments`, `attempts`). The trackpoints are never in `db`: every function that needs them takes a
`load_tps(session_id)` callable, so the matcher runs the same over a ride's file or a synthetic track.
"""
from __future__ import annotations

import math

from .engine import _geo, find_segment_passes, haversine_km, jround, now_iso


def _next_id(db: dict, kind: str) -> int:
    ids = db.setdefault("next_id", {})
    n = int(ids.get(kind) or 1)
    ids[kind] = n + 1
    return n


def get_segment(db: dict, seg_id) -> dict | None:
    return next((s for s in db.get("segments") or [] if s.get("id") == seg_id), None)


def get_session(db: dict, sid) -> dict | None:
    return next((s for s in db.get("sessions") or [] if s.get("id") == sid), None)


def record_segment_attempt(db: dict, a: dict) -> dict:
    """An attempt; when it beats the segment's PR, the segment takes it."""
    seg = get_segment(db, a["segment_id"])
    if not seg:
        raise ValueError("segment not found")
    is_pr = (not seg.get("pr_time_sec")) or a["time_sec"] < seg["pr_time_sec"]
    db.setdefault("attempts", []).append({
        "id": _next_id(db, "attempt"), "segment_id": a["segment_id"], "session_id": a["session_id"],
        "started_at": a.get("started_at"), "ended_at": a.get("ended_at"), "time_sec": a["time_sec"],
        "is_pr": 1 if is_pr else 0, "avg_hr": a.get("avg_hr"), "max_hr": a.get("max_hr"),
        "avg_speed_kmh": a.get("avg_speed_kmh"), "max_speed_kmh": a.get("max_speed_kmh"),
        "distance_m": a.get("distance_m"),
    })
    seg["attempts"] = int(seg.get("attempts") or 0) + 1
    if is_pr:
        seg.update(pr_time_sec=a["time_sec"], pr_session_id=a["session_id"], pr_at=now_iso())
    return {"isPr": bool(is_pr), "pr_time_sec": a["time_sec"] if is_pr else seg.get("pr_time_sec")}


def _attempt_from(seg_id, sid, p: dict) -> dict:
    return {"segment_id": seg_id, "session_id": sid, "started_at": p["started_at"], "ended_at": p["ended_at"],
            "time_sec": p["time_sec"], "avg_hr": p["avg_hr"], "max_hr": p["max_hr"],
            "avg_speed_kmh": p["avg_speed_kmh"], "max_speed_kmh": p["max_speed_kmh"], "distance_m": p["distance_m"]}


def process_session_segments(db: dict, session_id, load_tps, temp_at=None) -> dict:
    """Post-production: one ride × every segment. `load_tps(session_id)` gives its trackpoints; `temp_at(lat, lng,
    ts)` (optional, best-effort) the temperature it rode in."""
    session = get_session(db, session_id)
    tps = load_tps(session_id) if session else []
    if not session or not tps:
        return {"passes": []}
    if session.get("weather_temp_c") is None and temp_at and tps[0].get("lat") is not None:
        t = temp_at(tps[0]["lat"], tps[0]["lng"], tps[0]["ts"])
        if t is not None:
            session["weather_temp_c"] = t
    passes = []
    for seg in sorted(db.get("segments") or [], key=lambda s: -int(s.get("id") or 0)):   # ORDER BY id DESC
        for p in find_segment_passes(tps, seg):
            r = record_segment_attempt(db, _attempt_from(seg["id"], session_id, p))
            passes.append({"segment_id": seg["id"], "segment_name": seg.get("name"), **p,
                           "isPr": r["isPr"], "pr_time_sec": r["pr_time_sec"]})
    return {"passes": passes}


def backfill_segment_attempts(db: dict, segment_id, load_tps) -> dict:
    """Backfill: ONE segment × every finished ride, from scratch (idempotent); returns the ranking."""
    seg = get_segment(db, segment_id)
    if not seg:
        raise ValueError("segment not found")
    db["attempts"] = [a for a in db.get("attempts") or [] if a.get("segment_id") != segment_id]
    seg.update(pr_time_sec=None, pr_session_id=None, pr_at=None, attempts=0)
    ranking = []
    done = sorted((s for s in db.get("sessions") or [] if s.get("status") == "done"), key=lambda s: str(s.get("started_at")))
    for s in done:
        tps = load_tps(s["id"])
        if not tps:
            continue
        for p in find_segment_passes(tps, seg):
            r = record_segment_attempt(db, _attempt_from(segment_id, s["id"], p))
            ranking.append({"session_id": s["id"], "session_started_at": s.get("started_at"),
                            "weather_temp_c": s.get("weather_temp_c"), **p, "isPr": r["isPr"]})
    ranking.sort(key=lambda r: r["time_sec"])
    return {"segment": dict(seg), "ranking": ranking}


def list_session_attempts(db: dict, session_id) -> list:
    sess = get_session(db, session_id) or {}
    out = []
    for a in db.get("attempts") or []:
        if a.get("session_id") != session_id:
            continue
        seg = get_segment(db, a["segment_id"]) or {}
        out.append({**a, "segment_name": seg.get("name"), "segment_distance_m": seg.get("distance_m"),
                    "pr_time_sec": seg.get("pr_time_sec"), "weather_temp_c": sess.get("weather_temp_c")})
    return sorted(out, key=lambda a: str(a.get("started_at")))


def list_segment_attempts(db: dict, segment_id, limit: int = 50) -> list:
    out = []
    for a in db.get("attempts") or []:
        if a.get("segment_id") != segment_id:
            continue
        s = get_session(db, a["session_id"]) or {}
        out.append({**a, "temp_c": s.get("weather_temp_c"), "session_name": s.get("name")})
    return sorted(out, key=lambda a: str(a.get("started_at")), reverse=True)[:limit]


def refresh_segment_pr(db: dict, segment_id) -> None:
    """PR and count of a segment from the attempts it still has (after a ride is deleted)."""
    seg = get_segment(db, segment_id)
    if not seg:
        return
    mine = [a for a in db.get("attempts") or [] if a.get("segment_id") == segment_id and a.get("time_sec")]
    best = min(mine, key=lambda a: (a["time_sec"], str(a.get("started_at"))), default=None)
    for a in mine:
        a["is_pr"] = 1 if a is best else 0
    seg["attempts"] = len(mine)
    if best:
        seg.update(pr_time_sec=best["time_sec"], pr_session_id=best["session_id"])
    else:
        seg.update(pr_time_sec=None, pr_session_id=None, pr_at=None)


def segment_from_ride(trackpoints: list, start, end) -> dict | None:
    """What the segment editor saves: start and end snapped to the ride's nearest points, the real path between
    them (curves, not a straight line), its distance and its climb."""
    tps = _geo(trackpoints or [])
    if len(tps) < 2 or not start or not end:
        return None

    def find_idx(ll):
        bi, bd = 0, math.inf
        for i, p in enumerate(tps):
            d = (p["lat"] - ll[0]) ** 2 + (p["lng"] - ll[1]) ** 2
            if d < bd:
                bd, bi = d, i
        return bi

    i_s, i_e = find_idx(start), find_idx(end)
    a, b = min(i_s, i_e), max(i_s, i_e)
    sl = tps[a:b + 1]
    if len(sl) < 2:
        return None
    dist_m = gain = 0.0
    for i in range(1, len(sl)):
        dist_m += haversine_km(sl[i - 1]["lat"], sl[i - 1]["lng"], sl[i]["lat"], sl[i]["lng"]) * 1000
        if sl[i].get("altitude_m") is not None and sl[i - 1].get("altitude_m") is not None:
            d = sl[i]["altitude_m"] - sl[i - 1]["altitude_m"]
            if d > 0:
                gain += d
    s, e = tps[i_s], tps[i_e]
    return {"start_lat": s["lat"], "start_lng": s["lng"], "end_lat": e["lat"], "end_lng": e["lng"],
            "distance_m": jround(dist_m), "ele_gain_m": jround(gain), "polyline": [[p["lat"], p["lng"]] for p in sl]}


def point_at_km(trackpoints: list, km: float):
    """The ride's point where `km` of distance has been covered (for a segment said in kilometres)."""
    tps = _geo(trackpoints or [])
    if not tps:
        return None
    acc = 0.0
    for i in range(1, len(tps)):
        acc += haversine_km(tps[i - 1]["lat"], tps[i - 1]["lng"], tps[i]["lat"], tps[i]["lng"])
        if acc >= km:
            return [tps[i]["lat"], tps[i]["lng"]]
    return [tps[-1]["lat"], tps[-1]["lng"]]
