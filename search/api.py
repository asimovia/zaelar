"""search/api.py — the HTTP face of the search service (V2-782 T5.2).

    GET  /api/search/health[?fresh=1]   → {providers:[…], summary:{…}}   (cached 120 s; includes the Chromium)
    POST /api/search/find   {query, route?, k?, price_max?, price_min?, condition?, countries?, near?}
                                         → SearchResult.to_dict()
    POST /api/search/route  {query, proposal?, verdicts?}  → the Route alone, no network

One door for the turn, the worker (through its bridge), a MeshKore agent and the operator's own curl — so the
same code can later run as its own process behind the same paths. Guarded like every `/api/*` route by
`server/api_guard.py` (loopback or token). Blocking work runs in a thread: the browser bridge needs the loop free.
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger

from fastapi import APIRouter, Body

router = APIRouter()

_HEALTH_TTL_S = 120.0
_health_cache: dict = {"at": 0.0, "rows": []}


def cached_rows() -> list[dict]:
    """The last probe's rows, for the status panel — never probes on a poll (`/api/status` runs every 15 s)."""
    return list(_health_cache["rows"])


def prime_cache() -> None:
    """One probe at boot, so the panel has something to say before anyone asks.

    Where spending is bounded by an energy lease, the boot probe asks only the FREE indexes. Every paid probe is
    a real paid request, and a boot is not something anyone asked for: measured 2026-10-22, a brand-new account
    nobody had opened was billed for two web searches ~95 s after its machine started — this probe. The paid
    rows say `unprobed` until someone asks (`/api/search/health?fresh=1` or the CLI)."""
    from . import health as _health
    from .providers import PROVIDERS
    from .providers import keys as _keys
    try:
        skip = {n for n, p in PROVIDERS.items() if p.paid} if _keys.leased() else set()
        rows = _health.probe_all([n for n in PROVIDERS if n not in skip])
        rows += [{"provider": n, "kind": PROVIDERS[n].kind, "paid": True, "key": _keys.key_name(n), "ok": False,
                  "latency_ms": 0, "state": "unprobed", "why": "paid: probed on demand"} for n in sorted(skip)]
        _health_cache.update(at=time.time(), rows=rows)
    except Exception as e:  # noqa: BLE001 — a failed priming leaves the cache empty; the panel says «sin sondear»
        logger.warning(f"search.api: the boot probe failed ({e!r}); the panel will say «sin sondear todavía»")


def status_item() -> dict:
    """The ONE line of the status panel (V2-782 T2.2): live providers by name, or what is wrong."""
    from config.balances import say as _say

    from . import health as _health
    rows = cached_rows()
    if not rows:
        return {"key": "search", "label": _say("status.search.label", "Search · providers"), "state": "warn",
                "detail": _say("status.search.unprobed", "not probed yet")}
    s = _health.summary(rows)
    failing = ", ".join(f"{f['provider']} {f['state']}" for f in s["failing"])
    label = _say("status.search.label", "Search · providers")
    if not s["can_answer"]:
        none = _say("status.search.none", "none answering")
        return {"key": "search", "label": label, "state": "error", "detail": (none + " · " + failing) if failing else none}
    detail = _say("status.search.live", "live: {names}", names=", ".join(s["live"]))
    if failing:
        detail += " · " + failing
    return {"key": "search", "label": label, "state": "warn" if s["failing"] else "ok", "detail": detail}


@router.get("/api/search/health")
async def health(fresh: int = 0):
    from . import health as _health
    now = time.time()
    if fresh or not _health_cache["rows"] or now - _health_cache["at"] > _HEALTH_TTL_S:
        rows = await asyncio.to_thread(_health.probe_all)
        _health_cache.update(at=time.time(), rows=rows)
    rows = _health_cache["rows"]
    return {"providers": rows, "summary": _health.summary(rows), "cached_s": int(time.time() - _health_cache["at"])}


@router.post("/api/search/find")
async def find(body: dict = Body(...)):
    from . import find as _find
    b = body if isinstance(body, dict) else {}
    kw = {k: b.get(k) for k in ("price_max", "price_min") if b.get(k) is not None}
    res = await asyncio.to_thread(
        _find, str(b.get("query") or ""), route=b.get("route") or None, k=int(b.get("k") or 8),
        condition=str(b.get("condition") or ""), countries=tuple(b.get("countries") or ()),
        near=str(b.get("near") or ""), deadline_s=float(b.get("deadline_s") or 0.0),
        proposal=str(b.get("proposal") or ""), verdicts=b.get("verdicts") if isinstance(b.get("verdicts"), dict) else None,
        named_site=bool(b.get("named_site")), **kw)
    return res.to_dict()


@router.post("/api/search/route")
async def route(body: dict = Body(...)):
    from .route import search_route
    b = body if isinstance(body, dict) else {}
    rt = search_route(str(b.get("query") or ""), proposal=str(b.get("proposal") or ""),
                      verdicts=b.get("verdicts") if isinstance(b.get("verdicts"), dict) else None,
                      named_site=bool(b.get("named_site")))
    return rt.to_dict()
