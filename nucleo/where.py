"""nucleo/where.py — where a screen of the operator is NOW, in the agent's state (V2-875).

A screen (the desktop in a browser, the phone shell, the native app) reports a position when the person's
`privacy.location` switch is on AND the platform already granted it (`frontend/app/services/where.js`). Here:

  · the coordinates are rounded to 2 decimals (~1 km) before anything else — the state never holds a finer fix;
  · they are reverse geocoded to `place, region, country` (OpenStreetMap: Nominatim, Photon as the second door),
    cached per rounded cell, so a screen reporting every quarter of an hour costs one lookup per cell;
  · the result is the state's `here` — `{place, region, country, lat, lon, accuracy, at, dev}` — written through
    `memory.api.set_state`, which refreshes the cached prompt. `state.location` stays what the operator SAID is his
    home; `here` is where a screen of his is.

The prompt gets one line while `here` is fresh (`prompt_lines`); without `here` nor a home, the old «you do not know
where he lives» line. Turning the switch off clears `here` (`clear`). Every place resolved is handed to the PII
tagger, so stored events say [PLACE] instead of it.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

from loguru import logger

from connectors import outcome as _outcome

FRESH_S = 6 * 3600                 # a fix older than this says nothing about where he is now
_UA = "zaelar-personal-agent/1.0 (+https://zaelar.com)"
_cache: dict[tuple, dict] = {}


def _get(url: str, timeout: float = 5.0) -> dict | list | None:
    """GET a JSON answer through the one door that reports every outside call (`connectors/outcome.py`)."""
    host = urllib.parse.urlsplit(url).hostname or "geo"
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    raw = _outcome.call(f"where:{host}", "reverse", lambda: urllib.request.urlopen(req, timeout=timeout).read())  # noqa: S310
    return json.loads(raw.decode("utf-8"))


def reverse(lat: float, lon: float, lang: str = "") -> dict:
    """`{place, region, country}` for a rounded cell, or {} when nobody answers. Cached. Never raises."""
    key = (lat, lon, lang)
    if key in _cache:
        return _cache[key]
    out: dict = {}
    try:
        q = urllib.parse.urlencode({"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 10,
                                    "accept-language": lang or "en"})
        a = (_get("https://nominatim.openstreetmap.org/reverse?" + q) or {}).get("address") or {}
        place = a.get("city") or a.get("town") or a.get("village") or a.get("municipality") or a.get("county")
        if place:
            out = {"place": place, "region": a.get("state") or a.get("region") or "", "country": a.get("country", "")}
    except Exception as e:  # noqa: BLE001 — the second door
        logger.debug(f"where: nominatim reverse failed ({e!r})")
    if not out:
        try:
            q = urllib.parse.urlencode({"lat": lat, "lon": lon, "lang": (lang or "en")[:2]})
            feats = (_get("https://photon.komoot.io/reverse?" + q) or {}).get("features") or []
            p = (feats[0].get("properties") if feats else {}) or {}
            place = p.get("city") or p.get("town") or p.get("village") or p.get("name")
            if place:
                out = {"place": place, "region": p.get("state", ""), "country": p.get("country", "")}
        except Exception as e:  # noqa: BLE001 — a fix without a name still updates the coordinates
            logger.debug(f"where: photon reverse failed ({e!r})")
    if out:
        _cache[key] = out
    return out


def report(lat, lon, accuracy=None, dev: str = "") -> dict:
    """A screen's position → the state's `here`. `{ok, here}` or `{ok: False, reason}`."""
    from config import privacy
    if not privacy.location():
        return {"ok": False, "reason": "off"}
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return {"ok": False, "reason": "bad"}
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return {"ok": False, "reason": "bad"}
    lat, lon = round(lat, 2), round(lon, 2)
    geo = reverse(lat, lon, os.getenv("ZAELAR_LANGUAGE", ""))
    here = {**geo, "lat": lat, "lon": lon, "at": int(time.time()), "dev": str(dev or "")[:80]}
    try:
        here["accuracy"] = max(1000, int(round(float(accuracy or 0), -2)))   # never finer than the rounding
    except (TypeError, ValueError):
        here["accuracy"] = 1000
    from memory import api as memory
    memory.set_state({"here": here})
    try:
        from observability import pii
        pii.note_place(geo.get("place"), geo.get("region"))
    except Exception as e:  # noqa: BLE001 — the state is written; only the tagger misses this place
        logger.debug(f"where: place not handed to the tagger ({e!r})")
    return {"ok": True, "here": here}


def clear() -> None:
    """The switch went off: the state forgets where the screens are."""
    try:
        from memory import api as memory
        if (memory.state() or {}).get("here"):
            memory.set_state({"here": None})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"where: clear failed ({e!r})")


def fresh(state: dict, now: float | None = None) -> dict | None:
    h = (state or {}).get("here")
    if not isinstance(h, dict) or not h.get("place"):
        return None
    return h if ((now or time.time()) - float(h.get("at") or 0)) < FRESH_S else None


def prompt_lines(state: dict) -> list[str]:
    """The live tail's location lines: where a screen is now (fresh `here`), or the named gap when nothing is known."""
    h = fresh(state)
    if h:
        mins = max(1, int((time.time() - float(h["at"])) // 60))
        where = ", ".join(x for x in (h.get("place"), h.get("region"), h.get("country")) if x)
        return [f"AHORA el operador está en {where} (ubicación de su pantalla, hace {mins} min). Úsala para lo que "
                "dependa del lugar —cerca de mí, el tiempo, rutas, restaurantes—; su CASA sigue siendo la de su estado."]
    if not (state or {}).get("location"):
        return ["NO SABES dónde vive el operador (su ESTADO no tiene ubicación): no supongas ninguna "
                "ciudad ni la nombres; si hace falta para lo que te pide, pregúntasela."]
    return []
