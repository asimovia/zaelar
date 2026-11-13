"""Cycling engine — the ride maths, ported 1:1 from the source app's server module (V2-901).

Pure functions over trackpoints (`{"ts", "lat", "lng", "speed_kmh", "heart_rate", "altitude_m", "source", …}`): the
geometry, stats and splits, the segment matcher, heart-rate zones and the pure half of gap recovery. No I/O. The
store side (rides, segments, attempts, PRs) is `segments.py`. Every rounding goes through `jround`, because the original rounds with JavaScript's `Math.round`
(half up) and Python's `round` rounds half to even — a ranking that differs by one second is not the same port.
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timezone

R_KM = 6371.0


def jround(x: float, nd: int = 0) -> float:
    """JavaScript `Math.round(x * 10**nd) / 10**nd` (half rounds up, also for negatives)."""
    k = 10 ** nd
    v = math.floor(x * k + 0.5) / k
    return int(v) if nd == 0 else v


def ts_ms(t) -> float:
    """Milliseconds of a trackpoint timestamp: an ISO string with or without `Z` (a bare one is UTC), or a number."""
    if isinstance(t, (int, float)):
        return float(t)
    s = str(t or "").strip()
    if not s:
        return 0.0
    s = s.replace(" ", "T")
    if s.endswith("Z") or s.endswith("z"):
        s = s[:-1] + "+00:00"
    elif not (len(s) > 6 and s[-6] in "+-" and s[-3] == ":"):
        s += "+00:00"
    try:
        return datetime.fromisoformat(s).timestamp() * 1000.0
    except ValueError:
        return 0.0


def iso(ms: float) -> str:
    """`new Date(ms).toISOString()`."""
    d = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    return d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(d.microsecond / 1000):03d}Z"


def now_iso() -> str:
    return iso(time.time() * 1000.0)


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    return 2 * R_KM * math.asin(min(1.0, math.sqrt(a)))


def dist_meters(lat1, lng1, lat2, lng2) -> float:
    return haversine_km(lat1, lng1, lat2, lng2) * 1000.0


def seg_dist_meters(t_lat, t_lng, a_lat, a_lng, b_lat, b_lng) -> float:
    """Perpendicular distance (m) from a target point to the straight piece A–B (local equirectangular projection
    centred on the target: exact at the scale of tens of metres)."""
    rad, r = math.pi / 180, 6371000.0
    cos_lat = math.cos(t_lat * rad)
    ax, ay = (a_lng - t_lng) * rad * r * cos_lat, (a_lat - t_lat) * rad * r
    bx, by = (b_lng - t_lng) * rad * r * cos_lat, (b_lat - t_lat) * rad * r
    vx, vy = bx - ax, by - ay
    len2 = vx * vx + vy * vy
    t = -(ax * vx + ay * vy) / len2 if len2 else 0.0
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * vx, ay + t * vy
    return math.sqrt(cx * cx + cy * cy)


def dist_to_polyline_m(lat, lng, pts) -> float | None:
    """Shortest distance (m) from a point to a polyline of `[lat, lng]` (the live off-route check)."""
    if not pts or len(pts) < 2:
        return None
    best = math.inf
    for i in range(1, len(pts)):
        a, b = pts[i - 1], pts[i]
        if a[0] is None or b[0] is None:
            continue
        best = min(best, seg_dist_meters(lat, lng, a[0], a[1], b[0], b[1]))
    return None if best == math.inf else best


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def smooth_median(arr: list, window: int = 5) -> list:
    """Short moving median that ignores missing values; same length as the input (upper median, as the source)."""
    out: list = [None] * len(arr)
    half = window // 2
    for i in range(len(arr)):
        buf = sorted(arr[j] for j in range(max(0, i - half), min(len(arr) - 1, i + half) + 1) if _num(arr[j]))
        if buf:
            out[i] = buf[len(buf) // 2]
    return out


def _geo(tps: list) -> list:
    return [p for p in tps if p.get("lat") is not None and p.get("lng") is not None]


def compute_session_stats(trackpoints: list) -> dict | None:
    """Stats from the trackpoints: moving time (over 2 km/h), elevation ± on a smoothed altitude, gaps over 10 min
    left out, the speed cap at 100 km/h."""
    tps = _geo(trackpoints or [])
    if len(tps) < 2:
        return None
    dist_m = elev_gain = elev_loss = moving = max_speed = 0.0
    hr_sum = hr_count = hr_max = 0
    alt = smooth_median([p.get("altitude_m") for p in tps], 5)
    for i in range(1, len(tps)):
        a, b = tps[i - 1], tps[i]
        d_km = haversine_km(a["lat"], a["lng"], b["lat"], b["lng"])
        d_sec = (ts_ms(b["ts"]) - ts_ms(a["ts"])) / 1000
        if d_sec <= 0 or d_sec > 600:
            continue
        dist_m += d_km * 1000
        v = (d_km / d_sec) * 3600
        if max_speed < v < 100:
            max_speed = v
        if v > 2:
            moving += d_sec
        if alt[i] is not None and alt[i - 1] is not None:
            da = alt[i] - alt[i - 1]
            if da > 0:
                elev_gain += da
            else:
                elev_loss += -da
        hr = b.get("heart_rate")
        if _num(hr) and hr > 0:
            hr_sum += hr
            hr_count += 1
            hr_max = max(hr_max, hr)
    total = jround((ts_ms(tps[-1]["ts"]) - ts_ms(tps[0]["ts"])) / 1000)
    dist_km = dist_m / 1000
    avg = dist_km / (moving / 3600) if moving > 0 else 0
    return {
        "duration_sec": total,
        "moving_time_sec": jround(moving),
        "distance_km": jround(dist_km, 2),
        "avg_speed_kmh": jround(avg, 2),
        "max_speed_kmh": jround(max_speed, 2),
        "elevation_gain_m": jround(elev_gain),
        "elevation_loss_m": jround(elev_loss),
        "avg_hr": jround(hr_sum / hr_count) if hr_count else None,
        "max_hr": hr_max or None,
        "trackpoint_count": len(tps),
    }


def compute_session_splits(trackpoints: list, km_per_split: float = 1) -> list:
    """Splits by distance (1 km by default): time, speed, climb and mean heart rate of each."""
    tps = _geo(trackpoints or [])
    if len(tps) < 2:
        return []
    splits: list = []
    acc_km, start_idx, split_elev = 0.0, 0, 0.0
    last_alt = tps[0].get("altitude_m")
    for i in range(1, len(tps)):
        a, b = tps[i - 1], tps[i]
        acc_km += haversine_km(a["lat"], a["lng"], b["lat"], b["lng"])
        b_alt = b.get("altitude_m")
        if b_alt is not None and last_alt is not None:
            d = b_alt - last_alt
            if d > 0:
                split_elev += d
            last_alt = b_alt
        elif b_alt is not None:
            last_alt = b_alt
        if acc_km >= km_per_split:
            sl = tps[start_idx:i + 1]
            sec = jround((ts_ms(sl[-1]["ts"]) - ts_ms(sl[0]["ts"])) / 1000)
            hrs = [p["heart_rate"] for p in sl if _num(p.get("heart_rate")) and p["heart_rate"] > 0]
            splits.append({
                "idx": len(splits) + 1,
                "distance_km": jround(acc_km, 2),
                "duration_sec": sec,
                "avg_speed_kmh": jround(acc_km / (sec / 3600), 2) if sec > 0 else 0,
                "elevation_gain_m": jround(split_elev),
                "avg_hr": jround(sum(hrs) / len(hrs)) if hrs else None,
            })
            acc_km, start_idx, split_elev = 0.0, i, 0.0
    return splits


def find_segment_passes(trackpoints: list, seg: dict, threshold_m: float = 25) -> list:
    """Every pass of a segment inside a ride. The approach to a point is measured PERPENDICULAR to the route line
    (projection on each piece), not to the nearest vertex, so GPS sampling does not count and a narrow tolerance
    (~the real road) is enough. The mean speed uses the segment's CANONICAL distance, so a better time is always a
    better mean."""
    out: list = []
    if not trackpoints or seg.get("start_lat") is None or seg.get("end_lat") is None:
        return out
    tps = trackpoints

    def best_approach(target, frm):
        idx, best, entered = -1, math.inf, False
        for k in range(frm, len(tps)):
            d = dist_meters(tps[k]["lat"], tps[k]["lng"], target[0], target[1])
            if k > frm:
                de = seg_dist_meters(target[0], target[1], tps[k - 1]["lat"], tps[k - 1]["lng"], tps[k]["lat"], tps[k]["lng"])
                d = min(d, de)
            if d <= threshold_m:
                entered = True
                if d < best:
                    best, idx = d, k
            elif entered:
                break
        return idx

    i = 0
    while i < len(tps):
        i_start = best_approach((seg["start_lat"], seg["start_lng"]), i)
        if i_start == -1:
            break
        i_end = best_approach((seg["end_lat"], seg["end_lng"]), i_start + 3)
        if i_end == -1:
            break
        sl = tps[i_start:i_end + 1]
        time_sec = jround((ts_ms(sl[-1]["ts"]) - ts_ms(sl[0]["ts"])) / 1000)
        d_m = sum(dist_meters(sl[k - 1]["lat"], sl[k - 1]["lng"], sl[k]["lat"], sl[k]["lng"]) for k in range(1, len(sl)))
        hrs = [p["heart_rate"] for p in sl if _num(p.get("heart_rate")) and p["heart_rate"] > 0]
        speeds = [p["speed_kmh"] for p in sl if _num(p.get("speed_kmh")) and p["speed_kmh"] >= 0]
        avg_dist = seg.get("distance_m") or d_m
        out.append({
            "started_at": sl[0]["ts"], "ended_at": sl[-1]["ts"],
            "time_sec": time_sec, "distance_m": jround(d_m),
            "avg_hr": jround(sum(hrs) / len(hrs)) if hrs else None,
            "max_hr": max(hrs) if hrs else None,
            "avg_speed_kmh": jround((avg_dist / 1000) / (time_sec / 3600), 1) if time_sec > 0 else None,
            "max_speed_kmh": jround(max(speeds), 1) if speeds else None,
        })
        i = i_end + 1
    return out


# ── Heart-rate zones (the source's defaults: HR max = 220 − age) ──────────────────────────────────────────────────

def default_hr_zones(age) -> dict:
    mx = 220 - (int(age) if _num(age) and age > 0 else 30)
    return {
        "z1": {"min": 0, "max": jround(mx * 0.6), "name": "Recovery"},
        "z2": {"min": jround(mx * 0.6), "max": jround(mx * 0.7), "name": "Endurance"},
        "z3": {"min": jround(mx * 0.7), "max": jround(mx * 0.8), "name": "Tempo"},
        "z4": {"min": jround(mx * 0.8), "max": jround(mx * 0.9), "name": "Threshold"},
        "z5": {"min": jround(mx * 0.9), "max": mx, "name": "VO2 Max"},
        "hr_max": mx,
    }


def hr_zone_status(bpm, zmin, zmax) -> str:
    if not bpm or not zmin or not zmax:
        return "idle"
    if bpm < zmin:
        return "below"
    if bpm > zmax:
        return "above"
    return "in"


# ── Gap recovery (pure half of the source's gap-recovery module; the routing call is net.py's) ────────────────────

GAP_THRESHOLD_SEC = 30
SAMPLE_EVERY_SEC = 5


def gap_sec(prev_ts, curr_ts) -> int:
    return max(0, jround((ts_ms(curr_ts) - ts_ms(prev_ts)) / 1000))


def find_gaps(trackpoints: list, threshold_sec: int = GAP_THRESHOLD_SEC) -> list:
    out = []
    for i in range(1, len(trackpoints or [])):
        g = gap_sec(trackpoints[i - 1]["ts"], trackpoints[i]["ts"])
        if g > threshold_sec:
            out.append({"prev": trackpoints[i - 1], "curr": trackpoints[i], "gap_sec": g, "idx": i})
    return out


def interpolate_trackpoints(prev: dict, curr: dict, coords: list, every_sec: int = SAMPLE_EVERY_SEC) -> list:
    """Virtual trackpoints every `every_sec` along a routed line (`coords` as `[lng, lat]`), timestamps spread over
    the real time the gap lasted, at the stretch's mean speed. Strictly between `prev` and `curr`."""
    if not coords or len(coords) < 2:
        return []
    prev_ms, curr_ms = ts_ms(prev["ts"]), ts_ms(curr["ts"])
    total_ms = curr_ms - prev_ms
    if total_ms <= 0:
        return []
    cum = [0.0]
    for i in range(1, len(coords)):
        cum.append(cum[-1] + haversine_km(coords[i - 1][1], coords[i - 1][0], coords[i][1], coords[i][0]) * 1000)
    total_m = cum[-1]
    if total_m <= 0:
        return []
    avg_kmh = (total_m / 1000) / (total_ms / 3600000)
    n = max(2, math.floor(total_ms / 1000 / every_sec))
    out = []
    for i in range(1, n + 1):
        frac = i / (n + 1)
        target = frac * total_m
        k = 0
        while k < len(cum) - 2 and cum[k + 1] < target:
            k += 1
        s0, s1 = cum[k], cum[k + 1]
        f = (target - s0) / (s1 - s0) if s1 > s0 else 0
        out.append({
            "ts": iso(prev_ms + frac * total_ms),
            "lat": coords[k][1] + (coords[k + 1][1] - coords[k][1]) * f,
            "lng": coords[k][0] + (coords[k + 1][0] - coords[k][0]) * f,
            "speed_kmh": jround(avg_kmh, 1),
            "source": "reconstructed",
        })
    return out
