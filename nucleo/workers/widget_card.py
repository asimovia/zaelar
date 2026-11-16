"""A widget's card on demand: its declared actions and their fields, WITHOUT its data.

Measured: the worker's only way to learn a widget's actions was `read_widget`, which returns the manifest AND the
widget's data (up to 12 KB) — paid in context every time it only needed to know which action takes which field.
`card(wid)` is the declaration alone: what the widget is for, each action with its description, its declared
fields, whether it asks first and whether it leaves the machine, and each collection's fields (the shape the
generic `rows.*` door needs, no rows). The data stays behind `read`.
"""
from __future__ import annotations

from loguru import logger


def card(wid: str) -> dict:
    """`{"ok": True, "result": {...}}` with the widget's declaration, or `{"ok": False, "error": …}`."""
    try:
        from widgets import naming, runtime
        man = runtime.get(wid)
        if not man:
            _id, several = naming.resolve(wid)
            man = runtime.get(_id) if _id else None
            if not man:
                return {"ok": False, "error": naming.not_found(wid, several)}
            wid = _id
        from widgets import effects, rows
        acts = {}
        for name, spec in (man.get("actions") or {}).items():
            spec = spec if isinstance(spec, dict) else {}
            acts[name] = {"desc": str(spec.get("desc") or ""), "fields": dict(spec.get("payload") or {}),
                          **({"asks_first": True} if spec.get("confirm") else {}),
                          **({"leaves": True} if effects.leaves(wid, name) else {})}
        out = {"id": wid, "title": str(man.get("title") or wid), "for": str(man.get("whenToUse") or ""),
               "actions": acts}
        if (schema := rows.schema(wid)):
            out["collections"] = schema
        return {"ok": True, "result": out}
    except Exception as e:  # noqa: BLE001 — the card unread is said, never an empty success
        logger.debug(f"widget_card: {wid} unread ({e!r})")
        return {"ok": False, "error": f"card failed: {type(e).__name__}: {e}"}
