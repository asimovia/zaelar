"""The three open services the ride uses, each called from an action and never from the card (V2-901).

Open-Meteo (temperature during a ride, the weather window for readiness), Nominatim (the town a ride started in)
and OSRM (the road between two fixes when the GPS went blind). No keys. Every call is bounded so a whole action
stays inside the widget pool's budget, and every failure is `None` — a ride is never lost to a service.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

from .engine import jround, ts_ms

_UA = "zaelar-personal-agent/1.0 (+https://zaelar.com)"
TIMEOUT_S = 2.5
_NOMINATIM_GAP_S = 1.1          # Nominatim's rate limit: one call a second
_last_geo = [0.0]


def get_json(url: str, timeout: float = TIMEOUT_S):
    """One GET → parsed JSON. The single network door of the app (tests replace it)."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:     # noqa: S310 — fixed https hosts below
        return json.loads(r.read().decode("utf-8", "replace"))


def temp_at(lat: float, lng: float, iso_ts) -> float | None:
    """Temperature (°C, one decimal) at the hour nearest a moment of the last 92 days."""
    try:
        q = urllib.parse.urlencode({"latitude": f"{lat:.3f}", "longitude": f"{lng:.3f}", "hourly": "temperature_2m",
                                    "past_days": 92, "forecast_days": 1, "timezone": "auto"})
        j = get_json("https://api.open-meteo.com/v1/forecast?" + q)
        times = (j.get("hourly") or {}).get("time") or []
        temps = (j.get("hourly") or {}).get("temperature_2m") or []
        if not times:
            return None
        # Open-Meteo answers local times with `utc_offset_seconds`; compare on the same clock as the ride.
        off = float(j.get("utc_offset_seconds") or 0) * 1000
        target = ts_ms(iso_ts)
        best = min(range(len(times)), key=lambda i: abs(ts_ms(times[i]) - off - target))
        v = temps[best] if best < len(temps) else None
        return jround(v, 1) if isinstance(v, (int, float)) else None
    except Exception:  # noqa: BLE001 — best-effort, as in the source
        return None


def weather_window(lat: float, lng: float, hours: float) -> dict | None:
    """Now + the next `hours` (the ride's expected length): temperature, precipitation, rain probability, UV."""
    horizon = max(2, min(8, int(-(-(hours + 1) // 1))))
    try:
        q = urllib.parse.urlencode({"latitude": f"{lat:.3f}", "longitude": f"{lng:.3f}",
                                    "current": "temperature_2m,precipitation,weather_code",
                                    "hourly": "temperature_2m,precipitation_probability,uv_index",
                                    "forecast_hours": horizon, "timezone": "auto"})
        j = get_json("https://api.open-meteo.com/v1/forecast?" + q)
        cur, hourly = j.get("current") or {}, j.get("hourly") or {}
        return {"horizon": horizon, "t_now": cur.get("temperature_2m"), "precip_now": cur.get("precipitation") or 0,
                "temps": hourly.get("temperature_2m") or [], "probs": hourly.get("precipitation_probability") or [],
                "uv": hourly.get("uv_index") or []}
    except Exception:  # noqa: BLE001
        return None


def locality(lat: float, lng: float, lang: str = "en") -> str | None:
    """«Town» for a ride's start point (Nominatim, zoom 12), at most one call a second."""
    try:
        wait = _NOMINATIM_GAP_S - (time.time() - _last_geo[0])
        if wait > 0:
            time.sleep(min(wait, _NOMINATIM_GAP_S))
        _last_geo[0] = time.time()
        q = urllib.parse.urlencode({"format": "json", "zoom": 12, "accept-language": lang or "en",
                                    "lat": lat, "lon": lng})
        j = get_json("https://nominatim.openstreetmap.org/reverse?" + q)
        a = j.get("address") or {}
        place = (a.get("city") or a.get("town") or a.get("village") or a.get("county") or a.get("state")
                 or (str(j.get("display_name") or "").split(",")[0] or None))
        return str(place)[:60] if place else None
    except Exception:  # noqa: BLE001
        return None


def route(frm: dict, to: dict, profile: str = "cycling", timeout: float = TIMEOUT_S) -> dict | None:
    """The road between two fixes (OSRM public server): `{distance_m, duration_sec, coordinates:[[lng,lat]…]}`."""
    try:
        url = (f"https://router.project-osrm.org/route/v1/{profile}/{frm['lng']},{frm['lat']};{to['lng']},{to['lat']}"
               "?overview=full&geometries=geojson&steps=false")
        j = get_json(url, timeout)
        r = (j.get("routes") or [None])[0]
        if not r:
            return None
        return {"distance_m": r.get("distance") or 0, "duration_sec": r.get("duration"),
                "coordinates": (r.get("geometry") or {}).get("coordinates") or []}
    except Exception:  # noqa: BLE001
        return None
