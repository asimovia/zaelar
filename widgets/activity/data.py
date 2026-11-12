"""Activity — a ride, a run, a walk or a drive the person starts (V2-890 F1).

The screen that owns the activity reads the device's sensors through `ctx.device().activity()` (the native app
keeps reading with the screen locked) and sends them here in batches (`samples`). This module keeps the track,
derives the figures and answers every screen the same view. Storage: the shared per-widget store.

Rules: nothing starts by itself (`start` comes from his tap or his request); one activity at a time; a sample
from a screen that does not own the activity is refused; a reading we do not have is `None`, never a zero.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

from loguru import logger

from .. import store

WID = "activity"
DB_VERSION = 1
# The kinds of activity are DECLARED in the manifest (`kinds`), the one place the card and the catalogue read.
KINDS = json.loads((Path(__file__).with_name("manifest.json")).read_text())["kinds"]
TRACK_MAX = 20_000          # ~5.5 h at 1 Hz
HISTORY_MAX = 30
ROUTE_POINTS = 300          # what the view sends to draw the route
HR_RECENT_S = 15            # a heart rate older than this is not "now"
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
        "climb_m": round(cur["climb_m"]),
        "moving": cur["last_mode"],
        "has_location": bool(cur["track"]),
        "has_heart_rate": bool(cur["hr"]),
    }


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
        out = {"status": db.get("status", "idle"), "history": (db.get("history") or [])[:5]}
        if cur:
            out.update({"kind": cur["kind"], "label": cur["label"], "started_at": int(cur["started_at"] * 1000),
                        "owner": cur["owner"], "route": _route(cur["track"]), **_figures(cur, now)})
        return out
    except Exception as e:  # noqa: BLE001 — a broken store is an empty card that says so, never a dead turn
        return {"status": "idle", "history": [], "error": str(e)[:120]}


def _a_start(action: str, p: dict) -> dict:
    db = _load()
    if db.get("status") == "running" and db.get("current"):
        cur = db["current"]
        return {"ok": True, "already": True, "kind": cur["kind"], "status": "running"}
    kind = str(p.get("kind") or "cycling").lower()
    if kind not in KINDS:
        return {"ok": False, "error": f"unknown kind '{kind}'", "kinds": list(KINDS)}
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
               "elapsed_s": f["elapsed_s"], "distance_m": f["distance_m"], "avg_speed_kmh": f["avg_speed_kmh"],
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
    fn = ACTIONS.get(action)
    if not fn:
        return {"ok": False, "error": f"unknown action '{action}'", "actions": sorted(ACTIONS)}
    try:
        return fn(action, payload if isinstance(payload, dict) else {})
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:120]}


def prompt_digest() -> str:
    """With the card open: the running activity's figures, so «what's my heart rate?» needs no round trip."""
    try:
        v = view_data()
        if v.get("status") != "running":
            return ""
        bits = [f"{v['kind']} running for {v['elapsed_s'] // 60} min", f"{v['distance_m'] / 1000:.1f} km"]
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
        logger.warning(f"activity: prompt_digest failed: {e}")
        return ""
