"""Recording a ride: the sensor samples of the screen that owns it become figures and trackpoints (V2-901).

The source app ran this pipeline in the browser on every GPS fix. Here the samples come from the device bridge in
batches (`ctx.device().activity()`), and a locked phone hands over minutes of them at once, so the pipeline runs
in `data.py`, sample by sample in their own time order, and gives the same result however they were batched:

- a fix worse than 30 m (20 m while the GPS calibrates) is dropped, and so is one implying over 80 km/h;
- speed = the haversine speed over a rolling 6-second window blended 60/40 with the GPS's own speed, low-passed
  (0.65 old / 0.35 new), under 1 km/h is 0, capped at 80;
- the first 5 s (the countdown) and 2 s more only calibrate: nothing counts, the window starts again after them;
- distance grows by steps between 1 m and 500 m, and not while paused; a pause is an interval of TIME, so a batch
  that arrives after a pause is judged by when each sample was taken, not by when it arrived;
- a gap over 30 s between fixes is a blackout: the stretch is rebuilt along real roads (OSRM) as reconstructed
  trackpoints, or, failing that, counted as a straight line within a sanity cap — and counted only once (the source
  also added the direct step between the two fixes on top of it);
- a trackpoint is kept every 5 s (in the ride's own file) with the heart rate and altitude of that moment.
"""
from __future__ import annotations

from . import engine as E
from . import ghost as G
from . import net

COUNTDOWN_S = 5
WARMUP_AFTER_S = 2
PERSIST_EVERY_MS = 5000
BUF_MS = 6000
ACC_WARMUP_M = 20
ACC_RIDE_M = 30
OUTLIER_KMH = 80
CAP_KMH = 80
ALPHA = 0.65
HR_FRESH_MS = 15000
ROUTE_STEP_M = 8            # the live map's trace keeps a point every few metres
ROUTE_MAX = 1500


def new_ride(ride_id: int, now_ms: float, zone_min, zone_max, owner=None) -> dict:
    start = now_ms + COUNTDOWN_S * 1000
    return {
        "id": ride_id, "created_ms": now_ms, "started_ms": start, "started_at": E.iso(start),
        "countdown_until_ms": start, "warmup_until_ms": start + WARMUP_AFTER_S * 1000,
        "owner": owner, "last_seq": -1, "hr_zone_min": zone_min, "hr_zone_max": zone_max,
        "pauses": [], "was_paused": False, "buf": [], "buf_reset": False,
        "last_disp_speed": 0.0, "speed": 0.0, "max_speed": 0.0, "distance_km": 0.0,
        "last_lat": None, "last_lng": None, "last_acc": None, "altitude": None, "baro": None, "hr": None,
        "last_saved_ms": 0, "route": [], "n_tps": 0, "start_lat": None, "start_lng": None,
        "reconstructed": 0, "events": [], "ev_n": 0, "ghost": G.new_state(),
    }


def paused_at(cur: dict, t_ms: float) -> bool:
    return any(p[0] <= t_ms and (p[1] is None or t_ms < p[1]) for p in cur.get("pauses") or [])


def is_paused(cur: dict) -> bool:
    ps = cur.get("pauses") or []
    return bool(ps) and ps[-1][1] is None


def elapsed_s(cur: dict, now_ms: float) -> int:
    """Riding time: from the end of the countdown, without the pauses."""
    if now_ms <= cur["started_ms"]:
        return 0
    paused = sum((min(p[1] if p[1] is not None else now_ms, now_ms) - max(p[0], cur["started_ms"]))
                 for p in cur.get("pauses") or [] if (p[1] if p[1] is not None else now_ms) > cur["started_ms"])
    return max(0, E.jround((now_ms - cur["started_ms"] - max(0, paused)) / 1000))


def hr_now(cur: dict, t_ms: float):
    h = cur.get("hr")
    return h[1] if h and 0 <= t_ms - h[0] <= HR_FRESH_MS else None


def _keep_route(cur: dict, lat: float, lng: float) -> None:
    r = cur["route"]
    if r and E.dist_meters(r[-1][0], r[-1][1], lat, lng) < ROUTE_STEP_M:
        return
    r.append([round(lat, 6), round(lng, 6)])
    if len(r) > ROUTE_MAX:
        cur["route"] = r[::2] + ([r[-1]] if len(r) % 2 == 0 else [])   # thin it, always keeping where he is


def _gap(cur: dict, frm: dict, to: dict, gap_s: float, out: list, can_route: bool) -> bool:
    """A blackout: rebuild the stretch along real roads; else a straight line within a sanity cap. Returns whether
    the router was called (one routed gap per batch keeps the action inside its budget)."""
    rt = net.route(frm, to) if can_route else None
    if rt and rt.get("coordinates"):
        virt = E.interpolate_trackpoints(frm, to, rt["coordinates"])
        out.extend(virt)
        cur["reconstructed"] = int(cur.get("reconstructed") or 0) + len(virt)
        km = (rt.get("distance_m") or 0) / 1000
        if 0 < km < 50:
            cur["distance_km"] += km
        for c in rt["coordinates"]:
            _keep_route(cur, c[1], c[0])
        G._event(cur, "gap_rebuilt", km=E.jround(km, 2), points=len(virt), gap_sec=E.jround(gap_s))
    else:
        km = E.haversine_km(frm["lat"], frm["lng"], to["lat"], to["lng"])
        if 0.05 < km < 30:
            cur["distance_km"] += km
            G._event(cur, "gap_straight", km=E.jround(km, 2), gap_sec=E.jround(gap_s))
    return can_route


def take(cur: dict, samples: list, segments: list, pr_paths: dict | None = None) -> tuple[int, list]:
    """Feed a batch of samples. Returns (how many were new, the trackpoints to append to the ride's file)."""
    out: list = []
    taken = 0
    routed = False
    for s in sorted((x for x in samples or [] if isinstance(x, dict)), key=lambda x: (x.get("t") or 0)):
        seq = s.get("seq")
        if isinstance(seq, int):
            if seq <= cur["last_seq"]:
                continue                     # a batch sent twice (the retry after the locked screen) counts once
        taken += 1
        kind, t = s.get("kind"), float(s.get("t") or 0)
        if kind == "heart_rate":
            bpm = s.get("bpm")
            if isinstance(bpm, (int, float)) and 20 <= bpm <= 250:
                cur["hr"] = [t, int(bpm)]
        elif kind == "altitude":
            if isinstance(s.get("relative_m"), (int, float)):
                cur["baro"] = float(s["relative_m"])
        elif kind == "location":
            routed = _location(cur, s, t, out, segments, pr_paths, routed) or routed
    seqs = [x.get("seq") for x in samples or [] if isinstance(x, dict) and isinstance(x.get("seq"), int)]
    if seqs:
        cur["last_seq"] = max(cur["last_seq"], max(seqs))
    cur["n_tps"] = int(cur.get("n_tps") or 0) + len(out)
    return taken, out


def _location(cur, s, t, out, segments, pr_paths, routed) -> bool:
    lat, lng = s.get("lat"), s.get("lon", s.get("lng"))
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return False
    lat, lng = float(lat), float(lng)
    raw = s.get("speed_mps")
    raw = float(raw) if isinstance(raw, (int, float)) and raw >= 0 else None
    alt = s.get("altitude_m")
    alt = float(alt) if isinstance(alt, (int, float)) else cur.get("baro")
    acc = s.get("accuracy_m")
    acc = float(acc) if isinstance(acc, (int, float)) else None

    in_countdown = t < cur["countdown_until_ms"]
    in_warmup = in_countdown or t < cur["warmup_until_ms"]
    if not in_countdown and not cur.get("buf_reset"):
        cur["buf"], cur["last_disp_speed"], cur["buf_reset"] = [], 0.0, True   # calibration samples do not count
    if acc is not None and acc > (ACC_WARMUP_M if in_warmup else ACC_RIDE_M):
        return False
    paused = paused_at(cur, t)
    if cur.get("was_paused") and not paused:
        cur["buf"] = []                                  # a clean window after a pause: no «jump» on resume
    cur["was_paused"] = paused
    buf = cur["buf"]
    if buf:
        lt = buf[-1]
        d_sec = (t - lt[0]) / 1000
        if d_sec > 0 and (E.haversine_km(lt[1], lt[2], lat, lng) / d_sec) * 3600 > OUTLIER_KMH:
            return False                                 # the GPS jumped
    buf.append([t, lat, lng, raw, acc])
    while buf and buf[0][0] < t - BUF_MS:
        buf.pop(0)
    if in_warmup:
        return False

    smoothed = None
    if len(buf) >= 3:
        d_km = sum(E.haversine_km(buf[i - 1][1], buf[i - 1][2], buf[i][1], buf[i][2]) for i in range(1, len(buf)))
        d_sec = (buf[-1][0] - buf[0][0]) / 1000
        if d_sec > 0:
            hk = (d_km / d_sec) * 3600
            smoothed = raw * 3.6 * 0.6 + hk * 0.4 if raw is not None else hk
    elif raw is not None:
        smoothed = raw * 3.6
    if smoothed is None:
        return False
    smoothed = 0.0 if smoothed < 1.0 else min(smoothed, CAP_KMH)
    filtered = (cur.get("last_disp_speed") or 0) * ALPHA + smoothed * (1 - ALPHA)
    cur["last_disp_speed"] = filtered
    speed = E.jround(filtered, 2)

    called = gap = False
    la = cur.get("last_acc")
    if not paused and la:
        g = (t - la[0]) / 1000
        if g > E.GAP_THRESHOLD_SEC:
            gap = True
            called = _gap(cur, {"lat": la[1], "lng": la[2], "ts": E.iso(la[0])}, {"lat": lat, "lng": lng, "ts": E.iso(t)},
                          g, out, not routed)
    # The stretch across a blackout is counted ONCE, by the gap (the source also added this direct step: a double count).
    if not paused and not gap and cur.get("last_lat") is not None:
        km = E.haversine_km(cur["last_lat"], cur["last_lng"], lat, lng)
        if 0.001 < km < 0.5:
            cur["distance_km"] += km
    cur["last_lat"], cur["last_lng"] = lat, lng
    cur["last_acc"] = [t, lat, lng]
    if cur.get("start_lat") is None:
        cur["start_lat"], cur["start_lng"] = lat, lng
    if not paused:
        _keep_route(cur, lat, lng)
    cur["speed"] = 0.0 if paused else speed
    if not paused and speed > cur["max_speed"]:
        cur["max_speed"] = speed
    if alt is not None:
        cur["altitude"] = alt
    if not paused:
        G.tick(cur, segments, lat, lng, t, pr_paths)
    if not cur["last_saved_ms"] or t - cur["last_saved_ms"] > PERSIST_EVERY_MS:
        cur["last_saved_ms"] = t
        out.append({"ts": E.iso(t), "lat": lat, "lng": lng, "speed_kmh": speed, "heart_rate": hr_now(cur, t),
                    "distance_km": E.jround(cur["distance_km"], 3), "altitude_m": alt, "accuracy_m": acc,
                    "source": "gps"})
    return called


def summary(cur: dict, now_ms: float) -> dict:
    """What the source saved at «save»: riding time, distance, mean (over riding time) and top speed."""
    sec = elapsed_s(cur, now_ms)
    dist = cur["distance_km"]
    return {"duration_sec": sec, "distance_km": dist,
            "avg_speed_kmh": E.jround(dist / (sec / 3600), 1) if dist and sec else None,
            "max_speed_kmh": cur["max_speed"]}
