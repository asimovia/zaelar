"""nucleo/pulse/budgets.py — what each piece of the engine may hold, per DEPLOYMENT, as data (V2-891).

The voice, the body, the Brain Workers and the browser share one host, each with a budget and ceiling per deployment
(`config/resources.default.json` → `budgets.{local,cloud}`, under a deployment's own `config/resources.json`): `cloud`
for a hosted account (`ZAELAR_USER_ID`), else `local` (`ZAELAR_DEPLOYMENT` names it). The free floor is what the
declared `pieces` need (ceilings + reserve `mb`), the ratio of the total only a CAP: a 48 GB laptop is not held at
9.6 GB for 300-600 MB workers; a 2-8 GB host, like a block without `pieces`, keeps max(ratio · total, mb).
"""
from __future__ import annotations

import os

#: Used only when the declared file lacks the block (a broken or old deployment file): the same numbers it declares.
_FALLBACK = {
    "local": {"voice": {"mb": 300, "ceiling_mb": 400}, "body": {"mb": 900, "ceiling_mb": 1200},
              "worker": {"mb": 300, "ceiling_mb": 600}, "chromium": {"mb": 250, "ceiling_mb": 500},
              "free_floor": {"ratio": 0.2, "mb": 768}},
    "cloud": {"voice": {"mb": 300, "ceiling_mb": 400}, "body": {"mb": 700, "ceiling_mb": 900},
              "worker": {"mb": 300, "ceiling_mb": 450}, "chromium": {"mb": 250, "ceiling_mb": 400},
              "free_floor": {"ratio": 0.0, "mb": 200}},
}


def deployment() -> str:
    explicit = (os.getenv("ZAELAR_DEPLOYMENT") or "").strip().lower()
    if explicit in _FALLBACK:
        return explicit
    return "cloud" if (os.getenv("ZAELAR_USER_ID") or "").strip() else "local"


def table(pol: dict | None = None, which: str | None = None) -> dict:
    """The budget table of one deployment (`which`, default this one's)."""
    if pol is None:
        from nucleo.workers import envelope
        pol = envelope.policy()
    which = which or deployment()
    declared = ((pol or {}).get("budgets") or {}).get(which)
    return declared if isinstance(declared, dict) and declared else _FALLBACK.get(which, _FALLBACK["local"])


def budget(piece: str, pol: dict | None = None, which: str | None = None) -> dict:
    row = table(pol, which).get(piece) or _FALLBACK["local"].get(piece) or {}
    return {"mb": float(row.get("mb", 0)), "ceiling_mb": float(row.get("ceiling_mb", row.get("mb", 0)))}


def free_floor_mb(total_bytes: int, pol: dict | None = None, which: str | None = None, *, pressure=None):  # pressure: the pause ratio → where the host is SHORT
    ff = table(pol, which).get("free_floor") or {}
    key, ratio = ("pressure_pieces", pressure) if pressure is not None else ("pieces", ff.get("ratio", 0))
    reserve, cap = float(ff.get("mb", 0)), float(ratio) * total_bytes / 2 ** 20
    if not ff.get(key):
        return cap if pressure is not None else max(cap, reserve)
    if unknown := [p for p in ff[key] if not isinstance(table(pol, which).get(str(p)), dict)]:
        raise ValueError(f"free_floor.{key} names no declared piece: {unknown}")   # a typo never lowers the floor
    need = sum(budget(str(p), pol, which)["ceiling_mb"] for p in ff[key]) + reserve
    return min(need, cap) if pressure is not None else max(reserve, min(need, cap))


def declares_floor(pol: dict | None) -> bool:
    """Does this policy carry a budgets block (the per-deployment floor), or only the older flat keys?"""
    return isinstance((pol or {}).get("budgets"), dict) and bool((pol or {}).get("budgets"))
