"""widgets/start_steps.py — what a widget's store owes at the engine's START, before his first word.

A widget whose manifest declares `"background": {"on_start": true}` has `data.on_start()` run once per start of the
engine, in a thread (never on the loop). The step is IDEMPOTENT by contract — it runs at every start, and a start
that repeats it changes nothing — and isolated like a tick: one that fails is said and never holds the start.

Why it exists: a store's schema migration is LAZY (`store.load` upgrades what it reads and writes nothing), so a
migration that does real work — the contacts card folding the rows that are one person — ran again on every read
until somebody happened to save, and on an engine nobody wrote to it never reached the disk at all. A start step
does that work once, under the widget's own write lock, and saves it.
"""
from __future__ import annotations

import asyncio
import importlib

from loguru import logger


def declared(w: dict) -> bool:
    bg = (w or {}).get("background")
    return isinstance(bg, dict) and bg.get("on_start") is True


def run() -> dict:
    """Every declared step, one after another. `{widget id: what it answered, or the error}`. Never raises."""
    from widgets import runtime
    out: dict = {}
    for w in runtime.catalog():
        wid = str(w.get("id") or "")
        if not wid or not declared(w):
            continue
        try:
            fn = getattr(importlib.import_module(f"widgets.{wid}.data"), "on_start", None)
            if not callable(fn):
                logger.warning(f"start[{wid}] declares `on_start` but data.py has none; skipped")
                continue
            out[wid] = fn()
            logger.info(f"start[{wid}] → {out[wid]}")
        except Exception as e:  # noqa: BLE001 — said, and the start goes on
            out[wid] = {"error": f"{type(e).__name__}: {e}"}
            logger.warning(f"start[{wid}] failed: {e!r}")
        _emit(wid, out.get(wid))
    return out


def _emit(wid: str, got) -> None:
    try:
        from observability.identity import paced
        from voice.observer import emit
        with paced():                       # the engine's own work: it never counts as his activity
            emit("background", "on_start", text=f"{wid}: {got}"[:200], extra={"id": wid})
    except Exception as e:  # noqa: BLE001 — the step ran; only its line on the timeline is missing
        logger.debug(f"start[{wid}] not said on the timeline: {e!r}")


def start():
    """Schedule `run` off the loop (called in the server's lifespan). The task, for a strong reference."""
    return asyncio.create_task(asyncio.to_thread(run))
