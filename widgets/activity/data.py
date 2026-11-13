"""Activity — a ride, a run, a walk or a drive the person starts (V2-890 F1).

The screen that owns the activity reads the device's sensors through `ctx.device().activity()` (the native app
keeps reading with the screen locked) and sends them here in batches (`samples`). This module keeps the track,
derives the figures and answers every screen the same view. Storage: the shared per-widget store.

Rules: nothing starts by itself (`start` comes from his tap or his request); one activity at a time; a sample
from a screen that does not own the activity is refused; a reading we do not have is `None`, never a zero.
"""
from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path

from .. import store

WID = "activity"
DB_VERSION = 1
# The kinds of activity are DECLARED in the manifest (`kinds`), the one place the card and the catalogue read.
logger = logging.getLogger(__name__)   # stdlib only: the widget contract (`make test-widgets`)
KINDS = json.loads((Path(__file__).with_name("manifest.json")).read_text())["kinds"]
TRACK_MAX = 20_000          # ~5.5 h at 1 Hz
HISTORY_MAX = 30
ROUTE_POINTS = 300          # what the view sends to draw the route
HR_RECENT_S = 15            # a heart rate older than this is not "now"
HR_SPARK_S = 600            # the live heart-rate sparkline: the last ten minutes …
HR_SPARK_POINTS = 60        # … in at most this many points
WEEK_S = 8 * 86_400         # the summaries the 7-day distance bars need (one day of slack for the person's time zone)
MIN_STEP_M = 2.0            # GPS jitter under this is not distance
MAX_ACCURACY_M = 50.0       # a fix worse than this does not count for distance


def _default() -> dict:
    return {"status": "idle", "current": None, "history": [], "_v": DB_VERSION}


def _load() -> dict:
    return store.load(WID, _default(), version=DB_VERSION, migrate=lambda db, _v: db)


def _save(db: dict) -> None:
    store.save(WID, db)


def _new(kind: str, label: str) -> dict:
    return {"kind": kind, "label": label, "started_at": time.time(), "owner": None, "track": [], "hr": [],
            "distance_m": 0.0, "climb_m": 0.0, "last_alt": None, "last_mode": None, "last_seq": -1}


def _metres(a: list, b: list) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[1], a[2], b[1], b[2]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6_371_000 * 2 * math.asin(min(1.0, math.sqrt(h)))


def _take(cur: dict, s: dict) -> None:
    kind, t = s.get("kind"), float(s.get("t") or 0) / 1000.0
    if kind == "location" and isinstance(s.get("lat"), (int, float)) and isinstance(s.get("lon"), (int, float)):
        acc = s.get("accuracy_m")
        pt = [t, float(s["lat"]), float(s["lon"]), s.get("speed_mps")]
        if cur["track"] and (acc is None or acc <= MAX_ACCURACY_M):
            step = _metres(cur["track"][-1], pt)
            if step >= MIN_STEP_M:
                cur["distance_m"] += step
        cur["track"].append(pt)
        del cur["track"][:-TRACK_MAX]
    elif kind == "heart_rate" and isinstance(s.get("bpm"), (int, float)) and 20 <= s["bpm"] <= 250:
        cur["hr"].append([t, int(s["bpm"])])
        del cur["hr"][:-TRACK_MAX]
    elif kind == "altitude" and isinstance(s.get("relative_m"), (int, float)):
        alt = float(s["relative_m"])
        if cur["last_alt"] is not None and alt - cur["last_alt"] > 0.5:
            cur["climb_m"] += alt - cur["last_alt"]
        if cur["last_alt"] is None or abs(alt - cur["last_alt"]) > 0.5:
            cur["last_alt"] = alt
    elif kind == "motion_activity" and s.get("mode"):
        cur["last_mode"] = str(s["mode"])[:16]


def _figures(cur: dict, now: float) -> dict:
    elapsed = max(0, int(now - cur["started_at"]))
    hrs = [b for _, b in cur["hr"]]
    last_hr = cur["hr"][-1] if cur["hr"] else None
    speeds = [p[3] for p in cur["track"][-5:] if isinstance(p[3], (int, float)) and p[3] >= 0]
    return {
        "elapsed_s": elapsed,
        "distance_m": round(cur["distance_m"]),
        "avg_speed_kmh": round(cur["distance_m"] / elapsed * 3.6, 1) if elapsed > 30 and cur["distance_m"] > 0 else None,
        "speed_kmh": round(sum(speeds) / len(speeds) * 3.6, 1) if speeds else None,
        "heart_rate": last_hr[1] if last_hr and now - last_hr[0] <= HR_RECENT_S else None,
        "hr_avg": round(sum(hrs) / len(hrs)) if hrs else None,
        "hr_max": max(hrs) if hrs else None,
        "climb_m": round(cur["climb_m"]) if cur["last_alt"] is not None else None,   # no barometer: no climb, not 0
        "moving": cur["last_mode"],
        "has_location": bool(cur["track"]),
        "has_heart_rate": bool(cur["hr"]),
    }


def _hr_recent(hr: list, now: float) -> list:
    """The last minutes of heart rate as [[t_ms, bpm]], averaged into at most HR_SPARK_POINTS buckets."""
    pts = [p for p in hr if now - p[0] <= HR_SPARK_S]
    if not pts:
        return []
    step = max(1, math.ceil(len(pts) / HR_SPARK_POINTS))
    out = []
    for i in range(0, len(pts), step):
        chunk = pts[i:i + step]
        out.append([int(chunk[-1][0] * 1000), round(sum(b for _, b in chunk) / len(chunk))])
    return out


def _route(track: list) -> list:
    step = max(1, math.ceil(len(track) / ROUTE_POINTS))
    pts = track[::step]
    if track and pts[-1] is not track[-1]:
        pts.append(track[-1])
    return [[round(p[1], 6), round(p[2], 6)] for p in pts]


def view_data(q: str = "") -> dict:
    try:
        db = _load()
        cur, now = db.get("current"), time.time()
        hist = db.get("history") or []
        # `days`: what the 7-day distance bars need (start, distance) — the card buckets them by ITS local day
        days = [[h["started_at"], h["distance_m"]] for h in hist
                if isinstance(h.get("started_at"), (int, float)) and now * 1000 - h["started_at"] <= WEEK_S * 1000
                and isinstance(h.get("distance_m"), (int, float))]
        out = {"status": db.get("status", "idle"), "history": hist[:5], "days": days}
        if cur:
            out.update({"kind": cur["kind"], "label": cur["label"], "started_at": int(cur["started_at"] * 1000),
                        "owner": cur["owner"], "route": _route(cur["track"]), "hr_recent": _hr_recent(cur["hr"], now),
                        **_figures(cur, now)})
        return out
    except Exception as e:  # noqa: BLE001 — a broken store is an empty card that says so, never a dead turn
        return {"status": "idle", "history": [], "days": [], "error": str(e)[:120]}


#: The short words a payload carries for a kind (EN + ES) — the kinds themselves are the manifest's.
_WORDS = {"run": "running", "correr": "running", "walk": "walking", "caminar": "walking", "paseo": "walking",
          "ride": "cycling", "bike": "cycling", "bici": "cycling", "cycle": "cycling", "drive": "driving", "conducir": "driving"}


def _a_start(action: str, p: dict) -> dict:
    db = _load()
    if db.get("status") == "running" and db.get("current"):
        cur = db["current"]
        return {"ok": True, "already": True, "kind": cur["kind"], "status": "running"}
    said = str(p.get("kind") or p.get("type") or p.get("activity") or "").strip().lower()   # measured: `{"type": "walk"}`
    kind = said if said in KINDS else _WORDS.get(said, "")
    if not kind:   # never a default: an unnamed or unknown kind is asked, not recorded as a ride
        return {"ok": False, "error": f"unknown kind '{said}'" if said else "kind_required", "kinds": list(KINDS)}
    db["current"], db["status"] = _new(kind, str(p.get("label") or "")[:40]), "running"
    _save(db)
    return {"ok": True, "status": "running", "kind": kind}


def _a_stop(action: str, p: dict) -> dict:
    db = _load()
    cur = db.get("current")
    if not cur:
        return {"ok": True, "status": "idle", "note": "no activity was running"}
    f = _figures(cur, time.time())
    summary = {"kind": cur["kind"], "label": cur["label"], "started_at": int(cur["started_at"] * 1000),
               "elapsed_s": f["elapsed_s"], "distance_m": f["distance_m"] if f["has_location"] else None,
               "avg_speed_kmh": f["avg_speed_kmh"],
               "hr_avg": f["hr_avg"], "hr_max": f["hr_max"], "climb_m": f["climb_m"]}
    db["history"] = ([summary] + (db.get("history") or []))[:HISTORY_MAX]
    db["current"], db["status"] = None, "idle"
    _save(db)
    return {"ok": True, "status": "idle", "summary": summary}


def _a_claim(action: str, p: dict) -> dict:
    db = _load()
    cur, owner = db.get("current"), str(p.get("owner") or "")[:64]
    if not cur or not owner:
        return {"ok": False, "error": "no running activity to claim" if not cur else "owner is required"}
    if cur["owner"] and cur["owner"] != owner:
        return {"ok": False, "owned_by_another_screen": True}
    if not cur["owner"]:
        cur["owner"] = owner
        _save(db)
    return {"ok": True, "owner": owner}


def _a_samples(action: str, p: dict) -> dict:
    db = _load()
    cur = db.get("current")
    if not cur:
        return {"ok": False, "error": "no running activity"}
    if cur["owner"] != str(p.get("owner") or ""):
        return {"ok": False, "owned_by_another_screen": True}
    taken = 0
    for s in (p.get("samples") or [])[:5000]:
        if not isinstance(s, dict):
            continue
        seq = s.get("seq")
        if isinstance(seq, int) and seq <= cur["last_seq"]:
            continue                       # a batch sent twice (a retry after the screen came back) counts once
        if isinstance(seq, int):
            cur["last_seq"] = seq
        _take(cur, s)
        taken += 1
    _save(db)
    return {"ok": True, "taken": taken}


ACTIONS = dict(start=_a_start, stop=_a_stop, claim=_a_claim, samples=_a_samples)   # the manifest's action names


def apply_action(action: str, payload: dict) -> dict:
    fn = ACTIONS.get(action) if isinstance(action, str) else None
    if not fn:
        return {"ok": False, "error": "unknown_action", "action": action, "actions": sorted(ACTIONS)}
    try:
        return fn(action, payload if isinstance(payload, dict) else {})
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:120]}


def _summary_line(h: dict) -> str:
    when = time.strftime("%Y-%m-%d", time.localtime((h.get("started_at") or 0) / 1000))
    dist = f"{h['distance_m'] / 1000:.1f} km" if isinstance(h.get("distance_m"), (int, float)) else "no distance"
    hr = f", avg heart rate {h['hr_avg']}" if h.get("hr_avg") else ""
    return f"{h.get('kind')} {when} {dist} in {int(h.get('elapsed_s') or 0) // 60} min{hr}"


def prompt_digest() -> str:
    """With the card open: the running activity's figures, so «what's my heart rate?» / «how far have I gone?» need no
    round trip; at rest, the last activities, so «what did I do yesterday?» needs none either."""
    try:
        v = view_data()
        if v.get("status") != "running":
            last = [_summary_line(h) for h in (v.get("history") or [])[:3]]
            return ("Activity on screen: nothing recording. Last: " + "; ".join(last) + ".") if last else ""
        bits = [f"{v['kind']} running for {v['elapsed_s'] // 60} min",
                f"{v['distance_m'] / 1000:.1f} km" if v.get("has_location") else "no GPS fix yet"]
        if v.get("heart_rate") is not None:
            bits.append(f"heart rate {v['heart_rate']} bpm now (avg {v['hr_avg']}, max {v['hr_max']})")
        elif v.get("has_heart_rate"):
            bits.append("heart rate: strap not sending right now")
        else:
            bits.append("no heart-rate strap connected")
        if v.get("speed_kmh") is not None:
            bits.append(f"{v['speed_kmh']} km/h")
        return "Activity on screen: " + ", ".join(bits) + "."
    except Exception as e:  # noqa: BLE001 — a broken digest leaves the turn without the figures, never broken
        logger.warning("activity: prompt_digest failed: %s", e)
        return ""
