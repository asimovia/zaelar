"""What is true around the worker right now — a short block in its brief and ONE bridge act to refresh it.

Measured: a worker started blind to the engine's present — which channels are connected, which widgets are open,
which other tasks are in flight, which MeshKore clusters it belongs to — and spent model turns rediscovering it
(or worse, assumed a channel that was down). The dossier leaves the screen out on purpose (it is memory, not state),
so this is the state's own reader: four facts, names only, each read from its owner and isolated (an unreadable one
is left out, never guessed). `block()` rides in the brief; `python -m nucleo.cli.bridge act state` returns the same
snapshot fresh, so nothing in the brief has to be long.
"""
from __future__ import annotations

from loguru import logger

#: How many other tasks, open widgets and clusters the brief names, and its whole block's ceiling: the rest is a
#: refresh away (`act state`), so the live brief stays under `catalog.PROMPT_CEILING_CHARS`.
_TASKS_SHOWN = 3
_NAMES_SHOWN = 6
BLOCK_CAP = 420


def _note(what: str, e: Exception) -> None:
    logger.debug(f"state_now: {what} unread ({type(e).__name__}: {e})")


def channels() -> dict:
    """`{platform: status}` of his messaging channels (connected / off / starting / …)."""
    try:
        from config import connectors as cfg
        from connectors.messaging import control, store
        live = store.load().get("platforms", {}) or {}
        return {p: str((live.get(p) or {}).get("status") or ("off" if not cfg.public(p).get("enabled") else "starting"))
                for p in control.PLATFORMS}
    except Exception as e:  # noqa: BLE001
        _note("channels", e)
        return {}


def widgets() -> list[str]:
    """The widgets open on his screen now, as the canvas reports them."""
    try:
        from nucleo.flash import canvas_visibility
        return sorted(canvas_visibility.open_ids())
    except Exception as e:  # noqa: BLE001
        _note("widgets", e)
        return []


def tasks(own: str = "") -> list[dict]:
    """His other live tasks: `{id, title, state}` (waiting on him reads `waiting_him`), this one left out."""
    try:
        from nucleo.circuit import ledger, waits
        rows = ledger.store().tasks_where(limit=20)
    except Exception as e:  # noqa: BLE001
        _note("tasks", e)
        return []
    out = []
    for r in rows:
        if str(r.get("id") or "") == str(own or ""):
            continue
        st = str(r.get("state") or "")
        if st == "waiting" and str(r.get("waiting_for") or "") == waits.USER_ANSWER:
            st = "waiting_him"
        out.append({"id": str(r.get("id") or ""), "title": str(r.get("title") or r.get("goal") or "")[:40],
                    "state": st})
    return out


def clusters() -> list[dict]:
    """His MeshKore clusters: `{name, connected}` (the token never leaves the manager)."""
    try:
        from connectors.meshkore import get_manager
        return [{"name": str(c.get("name") or ""), "connected": bool(c.get("connected"))}
                for c in get_manager().clusters() if c.get("name")]
    except Exception as e:  # noqa: BLE001
        _note("clusters", e)
        return []


def snapshot(own: str = "") -> dict:
    return {"channels": channels(), "widgets": widgets(), "tasks": tasks(own), "clusters": clusters()}


def _names(items: list[str]) -> str:
    shown = items[:_NAMES_SHOWN]
    return ", ".join(shown) + (f" +{len(items) - len(shown)}" if len(items) > len(shown) else "")


def block(own: str = "") -> str:
    """The brief's lines (session language): one line per fact that has something to say, cut at `BLOCK_CAP`;
    '' when none has."""
    from nucleo.workers.prompts import catalog
    w = lambda k: catalog.words(f"state_now.{k}")   # noqa: E731
    snap = snapshot(own)
    lines = []
    if snap["channels"]:
        lines.append(w("channels").format(list=", ".join(f"{p} ({s})" for p, s in snap["channels"].items())))
    if snap["widgets"]:
        lines.append(w("widgets").format(list=_names(snap["widgets"])))
    if snap["tasks"]:
        shown = snap["tasks"][:_TASKS_SHOWN]
        more = len(snap["tasks"]) - len(shown)
        lines.append(w("tasks").format(list="; ".join(f"«{t['title'][:40]}» ({t['state']})" for t in shown)
                                       + (f" +{more}" if more > 0 else "")))
    if snap["clusters"]:
        lines.append(w("clusters").format(list=_names(
            [f"{c['name']} ({'connected' if c['connected'] else 'disconnected'})" for c in snap["clusters"]])))
    head = w("head")
    out = "\n".join([head, *[f"  · {x}" for x in lines]]) if lines and head and all(lines) else ""
    return out if len(out) <= BLOCK_CAP else out[:BLOCK_CAP - 1].rstrip() + "…"
