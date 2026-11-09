"""genome/absorb.py — a new generation reaches an EXISTING agent through the ordinary update (V2-859 T566).

On the first boot of a new generation (its identity differs from the one this install last booted), a learned row
the factory now ships, identical, is ABSORBED: it becomes the factory row. Everything else is left exactly as it is:

  · a learned row that DIFFERS from the factory stays until its own TTL — it is still this agent's evidence;
  · a learned row he DISABLED is his decision and is never touched;
  · a seed he disabled stays disabled — absorption never writes a seed row, and the importer is `INSERT OR IGNORE`;
  · the personal layer (rules, config, memory, contacts, an operator-pinned route) is not read here at all.

Routes have no factory layer today (a route is only ever learned), so absorption is aliases only; the day a
generation ships routes, they are absorbed by the same comparison. Rollback = the previous release: the absorbed
rows are factory rows of a pack that still declares them, or plain rows its importer leaves alone.
"""
from __future__ import annotations

import json

from loguru import logger

_KEY = "genome.identity"


def _gene(row: dict) -> None:
    try:
        from voice.observer import emit
        emit("gene", f"🧬 alias absorbed · {row.get('lang')} → factory", role="system",
             extra={"layer": "learned", "type": "alias", "key": f"{row.get('lang')}/{row.get('phrase')}",
                    "before": {"source": "learned", "status": row.get("status")},
                    "after": {"source": "seed", "status": row.get("status")}, "cause": "absorbed",
                    "evidence": f"hits {row.get('hits') or 0}"})
    except Exception as e:  # noqa: BLE001 — the event is an instrument; the row moved either way
        logger.debug(f"genome: gene event not emitted ({e!r})")


def absorb() -> int:
    """Fold every active learned alias the factory now ships, identical, into the factory. Returns how many."""
    from memory import api as memory
    from nucleo.actionmap import store as amap
    n, packs = 0, {}
    for row in memory.action_map_learned():
        if row.get("status") != "active":
            continue
        lang = row.get("lang") or ""
        packs.setdefault(lang, amap.factory(lang))
        try:
            mine = json.loads(row.get("action") or "")
        except ValueError:
            logger.debug(f"genome: learned row {row.get('id')} has no readable action; left as it is")
            continue
        shipped = packs[lang].get(row.get("phrase") or "")
        if shipped is not None and json.dumps(shipped, sort_keys=True) == json.dumps(mine, sort_keys=True):
            if memory.action_map_absorb(int(row["id"])):
                _gene(row)
                n += 1
    if n:
        amap.invalidate()
    return n


def on_boot(ident: dict, genesis: dict | None = None) -> int:
    """Absorb once per generation change; remember the identity this install booted. Never raises."""
    try:
        from memory import api as memory
        last = memory.kv_get(_KEY, None)
        if isinstance(last, dict) and last.get("hash") == ident.get("hash"):
            return 0
        n = absorb()
        memory.kv_set(_KEY, ident)
        logger.info(f"genome: generation {(last or {}).get('generation') if isinstance(last, dict) else None} → "
                    f"{ident.get('generation')} · {n} learned row(s) absorbed")
        return n
    except Exception as e:  # noqa: BLE001 — a failed absorption leaves learned rows learned, which is safe
        logger.warning(f"genome: absorption skipped ({e!r})")
        return 0
