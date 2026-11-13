"""Shared fixtures of the cycling app's tests: an isolated store, no network, synthetic GPS tracks."""
from __future__ import annotations

import math

import pytest

T0 = 1_800_000_000_000          # a fixed instant (ms) the synthetic rides start at
M_PER_DEG_LAT = 111_195.0


@pytest.fixture
def cyc(monkeypatch, tmp_path):
    """The app's data module on an empty store of its own; any network call fails like a service that is down."""
    from widgets import store
    from widgets.cycling import data, net
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    data._GHOST_CACHE.clear()

    def offline(*a, **k):
        raise OSError("offline in tests")
    monkeypatch.setattr(net, "get_json", offline)
    return data


def straight_track(n, speed_mps=6.0, lat0=41.40, lng0=2.10, every_s=5, t0=T0, alt0=100.0, climb_per_pt=0.0, hr=None,
                   slow=None):
    """A ride due north at a steady speed, one trackpoint every `every_s` seconds (the app keeps one per 5 s).
    `slow=(i0, i1, factor)` rides points i0..i1 slower."""
    from widgets.cycling.engine import iso
    pts, lat = [], lat0
    for i in range(n):
        v = speed_mps * (slow[2] if slow and slow[0] <= i <= slow[1] else 1)
        if i:
            lat += v * every_s / M_PER_DEG_LAT
        pts.append({"ts": iso(t0 + i * every_s * 1000), "lat": lat, "lng": lng0, "speed_kmh": round(v * 3.6, 2),
                    "heart_rate": hr if hr is None else hr + (i % 7), "altitude_m": alt0 + climb_per_pt * i,
                    "source": "gps"})
    return pts


def loc(seq, t_ms, lat, lng, acc=5.0, speed=None, alt=None):
    s = {"seq": seq, "kind": "location", "t": t_ms, "lat": lat, "lon": lng, "accuracy_m": acc}
    if speed is not None:
        s["speed_mps"] = speed
    if alt is not None:
        s["altitude_m"] = alt
    return s


def ride_samples(t_start, seconds, speed_mps=6.0, lat0=41.40, lng0=2.10, seq0=0, hr=130, every_s=1):
    """Device samples of a steady ride due north from `t_start` (ms): a fix and a heart rate every `every_s`."""
    out, lat, seq = [], lat0, seq0
    for i in range(0, seconds, every_s):
        if i:
            lat += speed_mps * every_s / M_PER_DEG_LAT
        seq += 1
        out.append(loc(seq, t_start + i * 1000, lat, lng0, speed=speed_mps, alt=100 + i * 0.05))
        if hr is not None:
            seq += 1
            out.append({"seq": seq, "kind": "heart_rate", "t": t_start + i * 1000, "bpm": hr})
    return out, lat, seq


def metres(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6_371_000 * 2 * math.asin(min(1.0, math.sqrt(h)))
