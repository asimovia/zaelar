"""The ghost rider, live (V2-901, ported from the source app's in-ride segment tracker).

On every accepted fix of a ride that is not paused, `tick` works out — for every segment at once, since segments
may overlap — which ones are near (1 km, drawn faded), which one is being approached (150 m, a warning), which
ones he is INSIDE (entered within 35 m of the start, left within 35 m of the end) and which ones he abandoned
(more than 50 m off the segment's real path for four fixes in a row — never on a straight fallback line, where a
curve would read as off-route). Progress inside a segment is the distance actually ridden since entering, never
the straight line to the start (on a loop that line lies). Entering, finishing, abandoning and approaching are
EVENTS the card shows once; finishing says the time against the PR.

The ghost's rivals — where each earlier attempt would be at this instant — are computed from the attempts at read
time (`rivals`), so every screen and the voice see the same race.
"""
from __future__ import annotations

from . import engine as E

ENTER_M = 35
EXIT_M = 35
APPROACH_M = 150
NEARBY_M = 1000
OFF_ROUTE_M = 50
OFF_ROUTE_CONFIRM = 4
EVENTS_MAX = 20


def new_state() -> dict:
    return {"inside": [], "nearby": [], "approach": None, "abandoned": [], "selected": None}


def polyline_for(seg: dict, pr_polyline: list | None = None) -> list | None:
    """The best path of a segment: the PR's real track when known, its own saved path, else start→end."""
    if pr_polyline and len(pr_polyline) >= 2:
        return [[p[0], p[1]] for p in pr_polyline]
    pl = seg.get("polyline")
    if isinstance(pl, list) and len(pl) >= 2:
        return [[p[0], p[1]] for p in pl if isinstance(p, (list, tuple)) and p and p[0] is not None]
    if seg.get("start_lat") is not None and seg.get("end_lat") is not None:
        return [[seg["start_lat"], seg["start_lng"]], [seg["end_lat"], seg["end_lng"]]]
    return None


def _event(cur: dict, kind: str, **kw) -> None:
    cur["ev_n"] = int(cur.get("ev_n") or 0) + 1
    cur.setdefault("events", []).append({"n": cur["ev_n"], "kind": kind, **kw})
    del cur["events"][:-EVENTS_MAX]


def tick(cur: dict, segments: list, lat: float, lng: float, t_ms: float, pr_paths: dict | None = None) -> None:
    g = cur.setdefault("ghost", new_state())
    segs = [s for s in segments or [] if s.get("start_lat") is not None and s.get("end_lat") is not None]
    if not segs:
        return
    pr_paths = pr_paths or {}
    with_dist = [{"seg": s, "d_start": E.dist_meters(lat, lng, s["start_lat"], s["start_lng"]),
                  "d_end": E.dist_meters(lat, lng, s["end_lat"], s["end_lng"])} for s in segs]
    by_id = {x["seg"]["id"]: x for x in with_dist}

    g["nearby"] = [{"id": x["seg"]["id"], "dist_m": E.jround(x["d_start"])}
                   for x in sorted(with_dist, key=lambda x: x["d_start"]) if x["d_start"] <= NEARBY_M]

    prev_ids = {s["id"] for s in g["inside"]}
    still, entered, exited, abandoned = [], [], [], []
    for ins in g["inside"]:
        d = by_id.get(ins["id"])
        if not d:
            continue
        if d["d_end"] <= EXIT_M:
            exited.append({**ins, "elapsed": E.jround((t_ms - ins["entered_ms"]) / 1000)})
            continue
        path = polyline_for(d["seg"], pr_paths.get(ins["id"]))
        if path and len(path) > 2:                      # > 2 ⇒ a real path, not the straight fallback
            off = E.dist_to_polyline_m(lat, lng, path)
            ins["off_route"] = (ins.get("off_route") or 0) + 1 if off is not None and off > OFF_ROUTE_M else 0
            if ins["off_route"] >= OFF_ROUTE_CONFIRM:
                abandoned.append(ins)
                if ins["id"] not in g["abandoned"]:
                    g["abandoned"].append(ins["id"])    # not re-armed for the rest of this ride (no flip-flop)
                continue
        still.append(ins)

    for x in with_dist:
        sid = x["seg"]["id"]
        if sid in prev_ids or sid in g["abandoned"]:
            continue
        if x["d_start"] <= ENTER_M:
            e = {"id": sid, "name": x["seg"].get("name"), "distance_m": x["seg"].get("distance_m") or None,
                 "pr_time_sec": x["seg"].get("pr_time_sec") or None, "entered_ms": t_ms, "dist_accum": 0.0,
                 "last": None, "off_route": 0}
            entered.append(e)
            still.append(e)
    g["inside"] = still

    for ins in still:
        if ins.get("last"):
            ins["dist_accum"] = (ins.get("dist_accum") or 0) + E.dist_meters(ins["last"][0], ins["last"][1], lat, lng)
        ins["last"] = [lat, lng]

    ids_inside = {s["id"] for s in still}
    for e in entered:
        _event(cur, "enter", segment=e["id"], name=e["name"])
        if not g.get("selected") or g["selected"] not in ids_inside:
            g["selected"] = e["id"]
    for ex in exited:
        delta = ex["elapsed"] - ex["pr_time_sec"] if ex.get("pr_time_sec") else None
        _event(cur, "finish", segment=ex["id"], name=ex["name"], time_sec=ex["elapsed"], delta_sec=delta)
        if g.get("selected") == ex["id"]:
            g["selected"] = still[0]["id"] if still else None
    for ab in abandoned:
        _event(cur, "abandon", segment=ab["id"], name=ab["name"])
        if g.get("selected") == ab["id"]:
            g["selected"] = still[0]["id"] if still else None

    cands = sorted((x for x in with_dist if x["seg"]["id"] not in ids_inside and x["d_start"] <= APPROACH_M),
                   key=lambda x: x["seg"].get("distance_m") or 0)
    if cands:
        a = cands[0]
        was_new = not g.get("approach") or g["approach"]["id"] != a["seg"]["id"]
        g["approach"] = {"id": a["seg"]["id"], "name": a["seg"].get("name"), "dist_m": E.jround(a["d_start"])}
        if was_new:
            _event(cur, "approach", segment=a["seg"]["id"], name=a["seg"].get("name"))
    else:
        g["approach"] = None


def select(cur: dict, seg_id) -> bool:
    g = cur.setdefault("ghost", new_state())
    if seg_id is None or any(s["id"] == seg_id for s in g["inside"]):
        g["selected"] = seg_id
        return True
    return False


def active(cur: dict) -> dict | None:
    """The segment shown in the panel: the selected one, while he is inside it."""
    g = cur.get("ghost") or {}
    return next((s for s in g.get("inside") or [] if s["id"] == g.get("selected")), None)


def rivals(active_seg: dict, attempts: list, now_ms: float) -> list:
    """Where each earlier attempt is against him right now: the second of THAT attempt at which it stood at his
    current progress, minus his elapsed time. > 0 ⇒ it is ahead of him; < 0 ⇒ he is ahead."""
    if not active_seg:
        return []
    elapsed = E.jround((now_ms - active_seg["entered_ms"]) / 1000)
    dist = active_seg.get("distance_m")
    progress = (min(dist, active_seg.get("dist_accum") or 0) / dist) if dist else 0
    out = []
    for a in attempts or []:
        if not a.get("time_sec"):
            continue
        delta = elapsed - a["time_sec"] * progress
        out.append({"id": a.get("id"), "delta_sec": delta, "time_sec": a["time_sec"], "is_pr": bool(a.get("is_pr")),
                    "session_id": a.get("session_id"), "session_name": a.get("session_name")})
    return out
