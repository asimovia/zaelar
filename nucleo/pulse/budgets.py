"""nucleo/pulse/budgets.py — what each piece of the engine may hold, per DEPLOYMENT, as data (V2-891).

The engine runs as several processes that share one host: the voice (`python -m voice.engine`), the body
(`python -m server`), the Brain Workers and the browser. Each has a declared memory budget and a ceiling, and the
host keeps a free floor — and the numbers are not the same on the operator's own machine (a laptop with other
programs, a model server, swap) and on a small hosted machine with no swap and nothing else on it. So the table
is per deployment, in `config/resources.default.json` → `budgets.{local,cloud}`, and a deployment overrides it in
its own `config/resources.json`. Nothing here is a constant of the code.

`deployment()` — `cloud` when this engine serves a hosted account (`ZAELAR_USER_ID` is set), `local` otherwise;
`ZAELAR_DEPLOYMENT` names it explicitly. `budget(piece)` → `{"mb", "ceiling_mb"}`; `free_floor_mb(total)` → the
free memory the host must keep, the larger of a ratio of the total and an absolute floor.
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


def free_floor_mb(total_bytes: int, pol: dict | None = None, which: str | None = None) -> float:
    ff = table(pol, which).get("free_floor") or {}
    return max(float(ff.get("ratio", 0)) * total_bytes / 2 ** 20, float(ff.get("mb", 0)))


def declares_floor(pol: dict | None) -> bool:
    """Does this policy carry a budgets block (the per-deployment floor), or only the older flat keys?"""
    return isinstance((pol or {}).get("budgets"), dict) and bool((pol or {}).get("budgets"))
