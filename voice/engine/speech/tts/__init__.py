"""TTS family — streaming, interruptible text-to-speech (remote or local).

V2-778 F0-7 — the table's `tts.failover` row is a MECHANISM, not a note. `build_tts()` builds the selected provider
AND the table's stand-in; when both build, LiveKit's own `FallbackAdapter` switches to the stand-in the moment a
synthesis fails for good (a 402 from a provider out of credit is exactly that), and when the selected one cannot
even be built (a missing key raises `ValueError` in the plugin) the stand-in serves alone. Before this, a missing
`INWORLD_API_KEY` failed the prewarm and a 402 left the voice mute until someone switched the panel by hand.

`active_provider()` names the backend that is producing audio NOW, so the metering hook bills the one that spoke.

`start_prewarm()` opens a remote TTS's connection ahead of its first synthesis. Every plugin's `prewarm()` schedules
its work on the RUNNING event loop (`asyncio.create_task`), and one may instead return the coroutine itself: called
where no loop runs (the worker's `setup_fnc`) it builds the coroutine, raises, and the connection is never opened.
So it is called only from the session's loop, and an awaitable it returns is scheduled, never dropped.
"""
from __future__ import annotations

import asyncio
import inspect
import logging

from ...core.config import SETTINGS
from ...core.registry import Registry

registry = Registry("TTS")
logger = logging.getLogger("zaelar.tts")

_ACTIVE: dict = {"name": ""}


def _stand_in(primary: str) -> str:
    """The table's failover provider for the voice, when it is a different provider we can build."""
    try:
        from config import models as _models
        row = _models.failover("tts") or {}
    except Exception:  # noqa: BLE001 — no table row means no stand-in, never a boot failure
        return ""
    name = str(row.get("provider") or "").strip()
    return name if name and name != primary and name in registry.names() else ""


def active_provider() -> str:
    """The provider producing audio now: the selected one until the adapter gave up on it."""
    return _ACTIVE["name"] or SETTINGS.tts_provider


def _note(msg: str, **extra) -> None:
    logger.warning(msg)
    try:
        from voice.observer import emit
        emit("alert", msg, role="system", extra={"cat": "tts", **extra})
    except Exception:  # noqa: BLE001
        pass


def build_tts():
    primary = SETTINGS.tts_provider
    _ACTIVE["name"] = primary
    backup = _stand_in(primary)
    try:
        first = registry.create(primary)
    except Exception as e:  # noqa: BLE001 — e.g. ValueError: the plugin found no API key
        if not backup:
            raise
        try:
            only = registry.create(backup)
        except Exception:  # noqa: BLE001
            raise e from None
        _ACTIVE["name"] = backup
        _note(f"🔇 TTS «{primary}» could not be built ({type(e).__name__}: {e}) — speaking with «{backup}»",
              provider=primary, stand_in=backup)
        return only
    if not backup:
        return first
    try:
        second = registry.create(backup)
    except Exception as e:  # noqa: BLE001 — a stand-in that cannot sound here is not offered, and that is SAID at boot
        _note(f"⚠️ TTS has no stand-in here: «{backup}» cannot sound ({type(e).__name__}: {e}) — "
              f"an outage of «{primary}» silences the voice", provider=primary, stand_in=backup, standin_missing=True)
        return first
    return _with_failover([(primary, first), (backup, second)])


_WARMING: set = set()   # strong refs: a scheduled prewarm task must not be garbage-collected mid-handshake


def _settled(task) -> None:
    _WARMING.discard(task)
    if not task.cancelled() and task.exception() is not None:
        logger.warning("TTS prewarm failed: %s", task.exception())


def start_prewarm(tts) -> bool:
    """Open `tts`'s connection now, in the running loop. True when a prewarm was started.

    Without a running loop nothing is called (calling would build a coroutine that never runs); the session's loop
    warms it instead. A `prewarm()` that returns an awaitable has it scheduled. A failure is logged, never raised."""
    pw = getattr(tts, "prewarm", None)
    if not callable(pw):
        return False
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        logger.info("TTS prewarm deferred to the session's loop (no running loop here)")
        return False
    try:
        res = pw()
    except Exception as e:  # noqa: BLE001 — a prewarm is an optimisation; the first synthesis connects anyway
        logger.warning("TTS prewarm failed (%s): %s", type(tts).__name__, e)
        return False
    if inspect.isawaitable(res):
        task = asyncio.ensure_future(res)
        _WARMING.add(task)
        task.add_done_callback(_settled)
    return True


def _with_failover(pairs):
    from livekit.agents.tts import FallbackAdapter

    class _Adapter(FallbackAdapter):
        def prewarm(self) -> None:
            for t in self._tts_instances:   # the stand-in too: a failover must not pay a cold handshake either
                start_prewarm(t)

    names = [n for n, _ in pairs]
    adapter = _Adapter([t for _, t in pairs], max_retry_per_tts=1)

    def _changed(ev) -> None:
        try:
            i = [t for _, t in pairs].index(ev.tts)
        except ValueError:
            return
        if not ev.available and _ACTIVE["name"] == names[i]:
            nxt = next((names[j] for j, s in enumerate(adapter._status) if s.available), names[i])
            _ACTIVE["name"] = nxt
            _note(f"🔇 TTS «{names[i]}» failed — speaking with «{nxt}»", provider=names[i], stand_in=nxt)
        elif ev.available and i == 0:
            _ACTIVE["name"] = names[0]

    adapter.on("tts_availability_changed", _changed)
    adapter._zaelar_providers = names   # live_tts re-points each voice in its own provider (2026-10-04)
    return adapter


def available() -> list[str]:
    return registry.names()


from . import cartesia, elevenlabs, inworld, kokoro, openai_tts  # noqa: E402,F401

__all__ = ["build_tts", "available", "registry", "active_provider"]
